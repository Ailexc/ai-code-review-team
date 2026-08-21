"""安全审查 Agent — 使用 Semgrep 进行静态安全分析 + LLM 智能分析"""

import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()

# Semgrep 规则集（按语言）
SEMGREP_RULESETS = {
    "python": [
        "p/python", "p/flask", "p/django", "p/sqlalchemy",
        "p/python_audit", "p/bandit",
    ],
    "javascript": ["p/javascript", "p/nodejs", "p/react", "p/expressjs"],
    "typescript": ["p/typescript", "p/nodejs", "p/react", "p/expressjs"],
    "java": ["p/java", "p/spring"],
    "go": ["p/golang"],
    "default": ["p/security-audit", "p/owasp-top-ten"],
}

# 严重程度映射
SEVERITY_MAP = {
    "ERROR": "critical",
    "WARNING": "warning",
    "INFO": "suggestion",
}

# LLM 分析提示词
SECURITY_PROMPT = """你是一个代码安全专家。请分析以下代码，找出安全漏洞和风险。

代码文件: {file_path}
```
{code_content}
```

请用 JSON 格式返回分析结果，格式如下:
```json
{{
    "findings": [
        {{
            "rule_id": "SEC-001",
            "severity": "critical/warning/suggestion",
            "message": "简短描述问题",
            "file_path": "文件路径",
            "line_number": 行号,
            "code_snippet": "问题代码片段",
            "suggestion": "修复建议"
        }}
    ]
}}
```

注意:
1. 只返回 JSON，不要有其他内容
2. 如果没有安全问题，返回空数组: {{"findings": []}}
3. severity 分为: critical (严重), warning (警告), suggestion (建议)
4. 重点关注: SQL注入、命令注入、XSS、硬编码密码、不安全的反序列化、eval使用等"""


class SecurityAgent(BaseAgent):
    """安全审查 Agent — 使用 Semgrep + LLM 进行安全扫描"""

    name = "security"
    description = "代码安全审查（Semgrep 静态分析 + LLM 智能分析）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行安全扫描（Semgrep + LLM）"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        # 选择规则集
        language = self._detect_language(path)
        rulesets = SEMGREP_RULESETS.get(language, SEMGREP_RULESETS["default"])

        findings = []

        # 1. Semgrep 静态分析
        for ruleset in rulesets:
            try:
                results = self._run_semgrep(path, ruleset, file_paths)
                findings.extend(results)
            except Exception as e:
                logger.warning("Semgrep 规则集执行失败", ruleset=ruleset, error=str(e))

        # 2. LLM 智能分析（如果配置了 API Key）
        try:
            llm_findings = await self._run_llm_analysis(path, file_paths)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM 分析失败，回退到 Semgrep 结果", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("安全扫描完成", path=project_path, findings=len(unique))
        return unique

    async def _run_llm_analysis(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """使用 LLM 进行智能安全分析（并发调用，限制并发数避免过慢）"""
        try:
            import asyncio

            from app.models.llm_config import LLMConfig
            from app.core.database import async_session_factory
            from sqlalchemy import select
            import httpx

            # 1. 获取 LLM 配置：优先启用且为默认且有 Key 的，否则退回到任一启用且有 Key 的
            async with async_session_factory() as db:
                result = await db.execute(
                    select(LLMConfig)
                    .where(
                        LLMConfig.is_enabled == True,
                        LLMConfig.api_key.isnot(None)
                    )
                    .order_by(LLMConfig.is_default.desc())
                )
                llm_config = result.scalars().first()

            if not llm_config:
                logger.info("未找到有效的 LLM 配置，跳过 LLM 分析")
                return []

            # 2. 收集要分析的文件（最多 5 个，每个截断到 5000 字符）
            files_to_analyze = []
            if file_paths:
                for fp in file_paths[:5]:
                    full_path = path / fp
                    if full_path.exists() and full_path.suffix in ('.py', '.js', '.ts', '.tsx', '.jsx'):
                        files_to_analyze.append((fp, full_path.read_text(errors='ignore')[:5000]))
            else:
                for ext in ('*.py', '*.js', '*.ts'):
                    for f in list(path.rglob(ext))[:10]:
                        if '/node_modules/' not in str(f) and '/__pycache__/' not in str(f):
                            rel_path = str(f.relative_to(path))
                            content = f.read_text(errors='ignore')[:5000]
                            files_to_analyze.append((rel_path, content))
                            if len(files_to_analyze) >= 5:
                                break
                    if len(files_to_analyze) >= 5:
                        break

            if not files_to_analyze:
                return []

            # 3. 并发调用 LLM（限制并发 3，避免 API 限流）
            base_url = llm_config.base_url or "https://api.xiaomimimo.com/v1"
            headers = {
                "Authorization": f"Bearer {llm_config.api_key}",
                "Content-Type": "application/json",
            }
            max_tokens = min(llm_config.max_tokens, 4096)

            async def _analyze_one(file_path: str, content: str) -> list[dict[str, Any]]:
                prompt = SECURITY_PROMPT.format(file_path=file_path, code_content=content)
                try:
                    async with httpx.AsyncClient(timeout=90) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers=headers,
                            json={
                                "model": llm_config.model,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": max_tokens,
                                "temperature": llm_config.temperature,
                            },
                        )
                    if resp.status_code != 200:
                        logger.warning("LLM API 调用失败", status=resp.status_code, file=file_path)
                        return []

                    reply = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    json_start = reply.find('{')
                    json_end = reply.rfind('}') + 1
                    if json_start < 0 or json_end <= json_start:
                        logger.warning("LLM 返回内容不含 JSON", file=file_path)
                        return []

                    result_data = json.loads(reply[json_start:json_end])
                    return [{
                        "rule_id": f.get("rule_id", "LLM-SEC"),
                        "severity": f.get("severity", "warning"),
                        "message": f.get("message", ""),
                        "file_path": f.get("file_path", file_path),
                        "line_start": f.get("line_number"),
                        "code_snippet": f.get("code_snippet", "")[:500],
                        "suggestion": f.get("suggestion", ""),
                    } for f in result_data.get("findings", [])]
                except json.JSONDecodeError:
                    logger.warning("LLM 返回的 JSON 解析失败", file=file_path)
                    return []
                except Exception as e:
                    logger.warning("LLM 分析单个文件失败", file=file_path, error=str(e))
                    return []

            sem = asyncio.Semaphore(3)

            async def _bounded(file_path: str, content: str) -> list[dict[str, Any]]:
                async with sem:
                    return await _analyze_one(file_path, content)

            results = await asyncio.gather(
                *[_bounded(fp, content) for fp, content in files_to_analyze]
            )
            findings = [f for sublist in results for f in sublist]

            logger.info("LLM 分析完成", files=len(files_to_analyze), findings=len(findings))
            return findings

        except ImportError:
            logger.info("数据库模块不可用，跳过 LLM 分析")
            return []

    def _run_semgrep(
        self,
        path: Path,
        config: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行单个 Semgrep 规则集"""
        cmd = [
            "semgrep", "scan",
            "--config", config,
            "--json",
            "--no-git-ignore",
            "--timeout", "30",
            "--max-target-bytes", "1000000",
        ]

        if file_paths:
            for fp in file_paths[:50]:  # 限制数量
                full_path = path / fp
                if full_path.exists():
                    cmd.append(str(full_path))
        else:
            cmd.append(str(path))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(path),
            )
        except subprocess.TimeoutExpired:
            logger.warning("Semgrep 超时", config=config)
            return []
        except FileNotFoundError:
            logger.error("semgrep 命令未找到")
            return []

        if result.returncode not in (0, 1):  # 1 = findings found
            logger.warning("Semgrep 异常退出", code=result.returncode, stderr=result.stderr[:500])
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_results(path, data)

    def _parse_results(self, path: Path, data: dict) -> list[dict[str, Any]]:
        """解析 Semgrep JSON 输出"""
        findings = []
        for result in data.get("results", []):
            severity_raw = result.get("extra", {}).get("severity", "WARNING")
            severity = SEVERITY_MAP.get(severity_raw, "warning")

            file_path = result.get("path", "")
            line_start = result.get("start", {}).get("line")

            # Semgrep 的 extra.lines 不可靠（可能返回占位符），优先从源文件按行号读取真实代码
            snippet = result.get("extra", {}).get("lines", "") or ""
            if not snippet.strip() or snippet.strip().lower() in ("requires login", "n/a"):
                snippet = self._extract_code_snippet(path, file_path, line_start)

            findings.append({
                "rule_id": result.get("check_id", ""),
                "severity": severity,
                "message": result.get("extra", {}).get("message", ""),
                "file_path": file_path,
                "line_start": line_start,
                "line_end": result.get("end", {}).get("line"),
                "code_snippet": snippet[:500],
                "suggestion": result.get("extra", {}).get("fix", "") or result.get("extra", {}).get("metadata", {}).get("fix", ""),
            })
        return findings

    def _extract_code_snippet(self, path: Path, file_path: str, line_start: int | None) -> str:
        """从源文件读取问题行附近的代码片段（Semgrep lines 字段不可靠时的兜底）"""
        if not line_start:
            return ""
        try:
            full = Path(file_path) if Path(file_path).is_absolute() else path / file_path
            if not full.exists():
                return ""
            lines = full.read_text(errors="ignore").splitlines()
            if not lines:
                return ""
            start = max(1, line_start - 1)
            end = min(len(lines), line_start + 3)
            return "\n".join(lines[start - 1:end])
        except Exception:
            return ""

    def _detect_language(self, path: Path) -> str:
        """检测项目主要语言"""
        indicators = {
            "python": ["*.py", "pyproject.toml", "setup.py", "requirements.txt"],
            "typescript": ["*.ts", "*.tsx", "tsconfig.json"],
            "javascript": ["*.js", "*.jsx", "package.json"],
            "java": ["*.java", "pom.xml", "build.gradle"],
            "go": ["*.go", "go.mod"],
        }

        scores: dict[str, int] = {}
        for lang, patterns in indicators.items():
            count = 0
            for pattern in patterns:
                if "*" in pattern:
                    count += len(list(path.rglob(pattern))[:100])
                else:
                    count += 1 if (path / pattern).exists() else 0
            scores[lang] = count

        if not scores or max(scores.values()) == 0:
            return "default"
        return max(scores, key=scores.get)

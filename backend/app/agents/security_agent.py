"""安全审查 Agent — 使用 Semgrep 进行静态安全分析 + LLM 智能分析"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()

# Semgrep 规则根目录（本地化，离线扫描）
# 规则来自官方 semgrep/semgrep-rules 仓库（backend/app/data/semgrep-rules），
# 无需每次联网下载 registry 规则，彻底离线、更快、规则更全面。
RULES_ROOT = Path(__file__).resolve().parent.parent / "data" / "semgrep-rules"

# Semgrep 规则集（按语言，本地目录路径）
# python 拆分为主要安全框架规则集（并行扫描，展示粒度更好）；其他语言整目录。
SEMGREP_RULESETS = {
    "python": [
        str(RULES_ROOT / "python/django"),
        str(RULES_ROOT / "python/flask"),
        str(RULES_ROOT / "python/sqlalchemy"),
        str(RULES_ROOT / "python/cryptography"),
        str(RULES_ROOT / "python/requests"),
        str(RULES_ROOT / "python/correctness"),
    ],
    "javascript": [str(RULES_ROOT / "javascript")],
    "typescript": [str(RULES_ROOT / "typescript")],
    "java": [str(RULES_ROOT / "java")],
    "go": [str(RULES_ROOT / "go")],
    "default": [
        str(RULES_ROOT / "python/django"),
        str(RULES_ROOT / "python/correctness"),
    ],
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

        # 1. Semgrep 静态分析（本地规则集并行扫描）
        # 注：_run_semgrep 使用同步 subprocess，必须放到线程池执行（asyncio.to_thread），
        # 否则会阻塞事件循环；多个规则集通过 asyncio.gather 并行，避免串行拖慢整体。
        # 可观测性：每个规则集记录一条子步骤（耗时 / 命中数 / 异常）。
        from app.services.review_steps import review_step_recorder

        async def _scan_one(ruleset: str) -> list[dict[str, Any]]:
            ruleset_short = ruleset.replace(str(RULES_ROOT) + "/", "")
            t0 = asyncio.get_event_loop().time()
            try:
                results = await asyncio.to_thread(
                    self._run_semgrep, path, ruleset, file_paths
                )
                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                try:
                    await review_step_recorder.record_tool_substep(
                        agent_name=self.name,
                        node_type="semgrep_ruleset",
                        action_text=f"🔍 Semgrep 规则集 {ruleset_short}：命中 {len(results)} 条（{duration_ms / 1000:.1f}s）",
                        duration_ms=duration_ms,
                        detail={"ruleset": ruleset, "findings": len(results)},
                    )
                except Exception:
                    pass
                return results
            except Exception as e:
                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                try:
                    await review_step_recorder.record_tool_substep(
                        agent_name=self.name,
                        node_type="semgrep_ruleset",
                        status="failed",
                        action_text=f"⚠️ Semgrep 规则集 {ruleset_short} 执行失败：{str(e)[:100]}",
                        duration_ms=duration_ms,
                        detail={"ruleset": ruleset, "error": str(e)},
                    )
                except Exception:
                    pass
                logger.warning("Semgrep 规则集执行失败", ruleset=ruleset, error=str(e))
                return []

        results_list = await asyncio.gather(*[_scan_one(r) for r in rulesets])
        for results in results_list:
            findings.extend(results)

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
        """使用 LLM 进行智能安全分析（并发调用，注入代码库上下文）"""
        try:
            from app.agents.llm_client import get_active_llm_config, run_llm_analysis
            from app.agents.utils import collect_code_files_for_llm
            from app.agents.context_enhancer import enhance_prompt

            config = await get_active_llm_config()
            if not config:
                logger.info("未找到有效的 LLM 配置，跳过 LLM 分析")
                return []

            files = collect_code_files_for_llm(path, file_paths)
            if not files:
                return []

            # 代码库上下文引擎由 ReviewFlow 统一构建并经 ContextVar 传入（并发安全）
            prompts = [
                (
                    fp,
                    enhance_prompt(
                        fp,
                        SECURITY_PROMPT.format(file_path=fp, code_content=content),
                    ),
                )
                for fp, content in files
            ]
            findings = await run_llm_analysis(config, prompts, default_rule="LLM-SEC")
            logger.info("LLM 分析完成", files=len(files), findings=len(findings))
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
            "--metrics", "off",  # 禁用遥测上报，避免联网失败导致异常退出
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
        from app.agents.utils import extract_code_snippet

        findings = []
        for result in data.get("results", []):
            severity_raw = result.get("extra", {}).get("severity", "WARNING")
            severity = SEVERITY_MAP.get(severity_raw, "warning")

            file_path = result.get("path", "")
            line_start = result.get("start", {}).get("line")

            # Semgrep 的 extra.lines 不可靠（可能返回占位符），优先从源文件按行号读取真实代码
            snippet = result.get("extra", {}).get("lines", "") or ""
            if not snippet.strip() or snippet.strip().lower() in ("requires login", "n/a"):
                snippet = extract_code_snippet(path, file_path, line_start)

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

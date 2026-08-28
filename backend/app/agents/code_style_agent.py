"""代码规范审查 Agent — Ruff 静态检查 + LLM 语义点评"""

import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.agents.utils import extract_code_snippet, collect_code_files_for_llm

logger = structlog.get_logger()

# Ruff 规则 → 严重程度映射（先精确后前缀）
RULE_SEVERITY = {
    "F821": "critical",    # 未定义名称
    "F811": "warning",     # 重定义
    "F401": "suggestion",  # 未使用 import
    "F841": "suggestion",  # 未使用变量
    "F": "warning",        # pyflakes 其余
    "E": "suggestion",     # pycodestyle
    "W": "suggestion",     # pycodestyle 警告
    "C": "warning",        # 复杂度
    "N": "suggestion",     # 命名
    "I": "nitpick",        # import 排序
    "UP": "suggestion",    # pyupgrade
    "B": "warning",        # flake8-bugbear
    "S": "warning",        # flake8-bandit
    "T20": "suggestion",   # print 语句
    "RUF": "suggestion",
}
DEFAULT_SEVERITY = "suggestion"

# LLM 规范点评提示词
STYLE_PROMPT = """你是一个代码规范与可维护性专家。请审查以下代码的代码质量，找出可改进之处。

代码文件: {file_path}
```
{code_content}
```

请用 JSON 格式返回分析结果，格式如下:
```json
{{
    "findings": [
        {{
            "rule_id": "STYLE-001",
            "severity": "warning/suggestion/nitpick",
            "message": "简短描述问题",
            "file_path": "文件路径",
            "line_number": 行号,
            "code_snippet": "问题代码片段",
            "suggestion": "改进建议"
        }}
    ]
}}
```

审查重点:
1. 命名规范（函数/变量/类名是否清晰、符合语言惯例）
2. 函数复杂度（是否过长、嵌套过深、职责单一、参数过多）
3. 重复代码（可提取的公共逻辑）
4. 类型注解（Python 中缺失的类型标注）
5. 可读性（魔法数字、全局变量、死代码等）

注意:
1. 只返回 JSON，不要有其他内容
2. 如果没有问题，返回空数组: {{"findings": []}}
3. severity 分为: warning (需要改进), suggestion (建议), nitpick (细节优化)
4. 每个问题必须给出具体、可执行的改进建议"""


class CodeStyleAgent(BaseAgent):
    """代码规范审查 Agent — Ruff 静态检查 + LLM 语义点评"""

    name = "code_style"
    description = "代码规范审查（Ruff 静态检查 + LLM 语义点评）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行代码规范扫描（Ruff + LLM）"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        findings = []

        # 1. 确定性规范检查（按语言路由到各生态标准工具；可观测性：记录子步骤）
        import time as _time
        from app.agents.context_enhancer import get_or_build_engine  # noqa: F401 (引擎由 Flow 注入)
        from app.services.review_steps import review_step_recorder

        language = self._detect_language(path)
        _t0 = _time.monotonic()
        try:
            if language == "python":
                lint_findings = self._run_ruff(path, file_paths)
            elif language in ("javascript", "typescript"):
                lint_findings = self._run_eslint(path, file_paths)
            elif language == "go":
                lint_findings = self._run_golangci_lint(path)
            else:
                lint_findings = self._run_ruff(path, file_paths)  # 兜底尝试 Ruff

            findings.extend(lint_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            tool_name = {"python": "Ruff", "javascript": "ESLint", "typescript": "ESLint", "go": "golangci-lint"}.get(language, "Ruff")
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="lint_check",
                    action_text=f"🔍 {tool_name} 静态检查（{language}）：命中 {len(lint_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(lint_findings), "language": language, "tool": tool_name},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("静态检查失败", error=str(e))

        # 2. LLM 语义点评（补充静态工具漏报）
        try:
            llm_findings = await self._run_llm_analysis(path, file_paths)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM 规范分析失败，回退到 Ruff 结果", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("规范扫描完成", path=project_path, findings=len(unique))
        return unique

    def _detect_language(self, path: Path) -> str:
        """检测项目主要语言（与 security_agent 同构）"""
        indicators = {
            "python": ["*.py", "pyproject.toml", "setup.py", "requirements.txt"],
            "typescript": ["*.ts", "*.tsx", "tsconfig.json"],
            "javascript": ["*.js", "*.jsx", "package.json"],
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

    # ESLint 输出 severity 映射（ESLint 2=error 1=warning）
    _ESLINT_SEVERITY = {2: "warning", 1: "suggestion"}

    def _run_eslint(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行 ESLint（JS/TS 规范检查事实标准）

        使用容器内全局安装的 eslint@9 + typescript-eslint；
        目标项目无本地依赖也能跑（内置推荐规则集）。
        """
        cmd = ["eslint", "--format", "json", "--no-error-on-unmatched-pattern"]
        targets = []
        if file_paths:
            exts = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
            targets = [str(path / fp) for fp in file_paths[:50]
                       if (path / fp).exists() and (path / fp).suffix.lower() in exts]
        if not targets:
            targets = [str(path)]
        cmd.extend(targets)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(path))
        except FileNotFoundError:
            logger.warning("eslint 命令未找到（镜像未安装 Node 工具链？），跳过 ESLint")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("ESLint 超时")
            return []

        if not result.stdout.strip():
            logger.warning("ESLint 无输出", stderr=result.stderr[:200])
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        findings: list[dict[str, Any]] = []
        for file_entry in data:
            rel = str(Path(file_entry.get("filePath", "")).relative_to(path)) if file_entry.get("filePath", "").startswith(str(path)) else file_entry.get("filePath", "")
            for msg in file_entry.get("messages", []):
                rule = msg.get("ruleId") or "ESLINT"
                findings.append({
                    "rule_id": f"TS-{rule}" if rule != "ESLINT" else "TS-ESLINT",
                    "severity": self._ESLINT_SEVERITY.get(msg.get("severity", 1), "suggestion"),
                    "message": f"{msg.get('message', '')}（{rule}）",
                    "file_path": rel,
                    "line_start": msg.get("line"),
                    "code_snippet": extract_code_snippet(str(path), rel, msg.get("line")),
                    "suggestion": "",
                })
        return findings

    # golangci-lint 输出 severity 映射
    _GO_SEVERITY = {"error": "warning", "warning": "suggestion"}

    def _run_golangci_lint(self, path: Path) -> list[dict[str, Any]]:
        """运行 golangci-lint（Go 官方推荐 meta-linter，聚合 govet/staticcheck 等）

        注意：v1.61 的 flag 是 --out-format（不是 --output-format）；
        --no-config + enable-only 固定核心 linter 集合，结果确定、速度快，
        且不受目标项目自带 .golangci.yml 干扰。
        运行时依赖容器内 Go 工具链（类型检查需要），缺失时优雅跳过。
        """
        cmd = [
            "golangci-lint", "run",
            "--out-format", "json",
            "--timeout", "3m",
            "--no-config",
            "--enable-only=errcheck,govet,ineffassign,staticcheck,gosimple,unused",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=200, cwd=str(path))
        except FileNotFoundError:
            logger.warning("golangci-lint 命令未找到（镜像未安装？），跳过 Go 规范检查")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("golangci-lint 超时")
            return []

        # golangci-lint 有发现时退出码为 1，输出仍为合法 JSON
        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        findings: list[dict[str, Any]] = []
        for issue in data.get("Issues", []) or []:
            rel = str(Path(issue.get("Pos", {}).get("Filename", "")).relative_to(path)) \
                if issue.get("Pos", {}).get("Filename", "").startswith(str(path)) \
                else issue.get("Pos", {}).get("Filename", "")
            from_linter = issue.get("FromLinter", "govet")
            findings.append({
                "rule_id": f"GO-{from_linter}",
                "severity": self._GO_SEVERITY.get(issue.get("Severity", "") or "warning", "suggestion"),
                "message": f"{issue.get('Text', '')}（{from_linter}）",
                "file_path": rel,
                "line_start": issue.get("Pos", {}).get("Line"),
                "code_snippet": extract_code_snippet(str(path), rel, issue.get("Pos", {}).get("Line")),
                "suggestion": "",
            })
        return findings

    async def _run_llm_analysis(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """使用 LLM 进行规范语义点评（并发调用，注入代码库上下文）"""
        try:
            from app.agents.llm_client import get_active_llm_config, run_llm_analysis
            from app.agents.utils import collect_code_files_for_llm
            from app.agents.context_enhancer import enhance_prompt

            config = await get_active_llm_config()
            if not config:
                logger.info("未找到有效的 LLM 配置，跳过 LLM 点评")
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
                        STYLE_PROMPT.format(file_path=fp, code_content=content),
                    ),
                )
                for fp, content in files
            ]
            findings = await run_llm_analysis(config, prompts, default_rule="LLM-STYLE")
            logger.info("LLM 规范点评完成", files=len(files), findings=len(findings))
            return findings

        except ImportError:
            logger.info("数据库模块不可用，跳过 LLM 点评")
            return []

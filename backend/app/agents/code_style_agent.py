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

        # 1. Ruff 静态检查（确定性工具层；可观测性：记录子步骤）
        import time as _time
        from app.services.review_steps import review_step_recorder

        _t0 = _time.monotonic()
        try:
            ruff_findings = self._run_ruff(path, file_paths)
            findings.extend(ruff_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="ruff_check",
                    action_text=f"🔍 Ruff 静态检查：命中 {len(ruff_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(ruff_findings)},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("Ruff 检查失败", error=str(e))

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

    def _run_ruff(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行 Ruff 静态检查"""
        cmd = ["ruff", "check", "--output-format", "json", "--no-cache"]

        if file_paths:
            for fp in file_paths[:50]:
                full = path / fp
                if full.exists():
                    cmd.append(str(full))
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
            logger.warning("Ruff 超时")
            return []
        except FileNotFoundError:
            logger.error("ruff 命令未找到")
            return []

        if result.returncode not in (0, 1):  # 0=无问题 1=有问题
            logger.warning("Ruff 异常退出", code=result.returncode, stderr=result.stderr[:300])
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_results(path, data)

    def _parse_results(self, path: Path, data: list) -> list[dict[str, Any]]:
        """解析 Ruff JSON 输出"""
        findings = []
        for item in data:
            rule_code = item.get("code", "")
            line = item.get("location", {}).get("row")
            file_path = item.get("filename", "")
            message = item.get("message", "")
            fixable = bool(item.get("fix"))
            snippet = extract_code_snippet(path, file_path, line)

            findings.append({
                "rule_id": rule_code,
                "severity": self._map_severity(rule_code),
                "message": f"[{rule_code}] {message}" if rule_code else message,
                "file_path": file_path,
                "line_start": line,
                "code_snippet": snippet[:500],
                "suggestion": self._suggestion_for(rule_code, fixable),
                "is_auto_fixable": fixable,
                "fix_suggestion": self._suggestion_for(rule_code, fixable),
            })
        return findings

    def _map_severity(self, rule_code: str) -> str:
        """将 Ruff 规则代码映射为审查严重程度"""
        if rule_code in RULE_SEVERITY:
            return RULE_SEVERITY[rule_code]
        for prefix, severity in RULE_SEVERITY.items():
            if rule_code.startswith(prefix):
                return severity
        return DEFAULT_SEVERITY

    def _suggestion_for(self, rule_code: str, fixable: bool) -> str:
        """为 Ruff 规则生成修复建议"""
        if fixable:
            return f"Ruff 可自动修复（规则 {rule_code}），可运行 `ruff check --fix` 处理"
        return f"参考 Ruff 规则 {rule_code} 的说明手工修复"

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

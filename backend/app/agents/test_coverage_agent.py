"""测试覆盖审查 Agent — AST 未测试函数识别 + LLM 测试建议

确定性分析层：
- 解析项目源码 AST，提取全部函数/方法定义
- 识别测试文件（test_*.py / *_test.py），扫描其对函数名的引用
- 标记未被任何测试覆盖的函数
LLM 补充：为关键未测试函数生成测试用例建议。
"""

import ast
import re
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()

# 测试文件名模式
TEST_FILE_PATTERN = re.compile(r"(^|_)(test|spec)_.*\.py$|.*_(test|spec)\.py$")
TEST_DIR_NAMES = {"tests", "test", "spec", "__tests__"}

TEST_COVERAGE_PROMPT = """你是一个测试工程专家。请分析以下 Python 源码文件，为缺少测试的关键函数生成测试建议。

源码文件: {file_path}
```
{code_content}
```

请用 JSON 格式返回分析结果：
```json
{{
    "findings": [
        {{
            "rule_id": "TEST-001",
            "severity": "suggestion/warning",
            "message": "简短描述（如：函数 X 缺少单元测试）",
            "file_path": "文件路径",
            "line_number": 行号,
            "code_snippet": "相关函数签名",
            "suggestion": "建议的测试用例或测试场景"
        }}
    ]
}}
```

注意:
1. 只返回 JSON，不要有其他内容
2. 为每个缺少测试的关键函数给出建议（边界值、异常路径、正常路径）
3. severity: warning（关键业务逻辑未测试）, suggestion（辅助函数未测试）
4. 如果函数已有完善测试可跳过"""


class TestCoverageAgent(BaseAgent):
    """测试覆盖审查 Agent"""

    name = "test_coverage"
    description = "测试覆盖审查（AST 未测试函数识别 + LLM 测试建议）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        findings: list[dict[str, Any]] = []

        # 1. AST 静态分析：识别未测试函数（可观测性：记录子步骤）
        import time as _time
        from app.services.review_steps import review_step_recorder

        _t0 = _time.monotonic()
        try:
            ast_findings = self._analyze_coverage(path)
            findings.extend(ast_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="ast_coverage",
                    action_text=f"🔍 AST 覆盖分析：识别 {len(ast_findings)} 个未测试函数（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(ast_findings)},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("AST 覆盖分析失败", error=str(e))

        # 2. LLM 测试建议（针对未测试函数的源码）
        try:
            llm_findings = await self._run_llm_analysis(path)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM 测试建议失败，回退到 AST 结果", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("测试覆盖分析完成", path=project_path, findings=len(unique))
        return unique

    def _analyze_coverage(self, path: Path) -> list[dict[str, Any]]:
        """AST 静态分析：识别未被测试覆盖的函数"""
        # 收集测试文件中引用的函数名集合
        test_refs: set[str] = set()
        source_files: list[Path] = []

        for py in path.rglob("*.py"):
            rel = py.relative_to(path)
            parts = rel.parts
            if any(p in TEST_DIR_NAMES for p in parts) or TEST_FILE_PATTERN.match(py.name):
                try:
                    tree = ast.parse(py.read_text(errors="ignore"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Name):
                            test_refs.add(node.id)
                        elif isinstance(node, ast.Attribute):
                            test_refs.add(node.attr)
                except SyntaxError:
                    continue
            else:
                if not any(p.startswith(".") or p in {"__pycache__", "venv", ".venv"} for p in parts):
                    source_files.append(py)

        findings = []
        for src in source_files:
            try:
                tree = ast.parse(src.read_text(errors="ignore"))
            except SyntaxError:
                continue

            rel_path = str(src.relative_to(path))
            for node in ast.walk(tree):
                func_name = None
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_name = node.name
                    # 跳过魔术方法、私有helper、测试自身的函数
                    if func_name.startswith("_") or func_name.startswith("test_"):
                        continue

                    if func_name not in test_refs:
                        snippet = self._func_signature(src, node)
                        findings.append({
                            "rule_id": f"NO-TEST-{func_name}",
                            "severity": "suggestion",
                            "message": f"函数 `{func_name}` 未见任何测试引用",
                            "file_path": rel_path,
                            "line_start": node.lineno,
                            "code_snippet": snippet[:500],
                            "suggestion": f"为 `{func_name}` 补充单元测试，覆盖正常路径、边界值与异常场景",
                        })

        # 标记无测试目录的项目
        has_tests = any(
            any(p in TEST_DIR_NAMES for p in py.relative_to(path).parts) or TEST_FILE_PATTERN.match(py.name)
            for py in path.rglob("*.py")
        )
        if source_files and not has_tests:
            findings.append({
                "rule_id": "NO-TESTS-DIR",
                "severity": "warning",
                "message": "项目未发现测试目录或测试文件",
                "file_path": str(path),
                "line_start": None,
                "code_snippet": "",
                "suggestion": "建立 tests/ 目录并为核心模块编写单元测试（pytest）",
            })

        return findings

    def _func_signature(self, src: Path, node: ast.FunctionDef) -> str:
        """提取函数签名附近的代码片段"""
        try:
            lines = src.read_text(errors="ignore").splitlines()
            start = node.lineno - 1
            end = min(len(lines), start + 8)
            return "\n".join(lines[start:end])
        except Exception:
            return ""

    async def _run_llm_analysis(self, path: Path) -> list[dict[str, Any]]:
        """LLM 测试建议"""
        try:
            from app.agents.llm_client import get_active_llm_config, run_llm_analysis
            from app.agents.utils import collect_code_files_for_llm

            config = await get_active_llm_config()
            if not config:
                return []

            files = collect_code_files_for_llm(path, max_files=3, max_chars=4000)
            if not files:
                return []

            prompts = [
                (fp, TEST_COVERAGE_PROMPT.format(file_path=fp, code_content=content))
                for fp, content in files
            ]
            return await run_llm_analysis(config, prompts, default_rule="LLM-TEST")
        except ImportError:
            return []

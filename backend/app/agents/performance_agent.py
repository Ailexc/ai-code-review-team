"""性能分析审查 Agent — AST 识别 Python 性能反模式 + LLM 语义补充

检测维度：
1. N+1 查询 — 循环内 ORM 调用（session.query / .filter / .get 等）
2. 全表扫描 — .all() / .first() 无 filter 条件
3. 同步阻塞 — async 函数内 time.sleep / requests.get / subprocess.run
4. 低效拼接 — 循环内字符串 += 拼接
5. 无限制查询 — .all() 无 .limit() 配合
"""

import ast
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.agents.utils import extract_code_snippet, collect_code_files_for_llm

logger = structlog.get_logger()

# ORM 调用模式（方法名 → 说明）
ORM_CALL_METHODS = {
    "query", "filter", "filter_by", "get", "all", "first", "one",
    "execute", "scalar", "scalars", "select", "where",
    "objects", "find", "find_by",  # Django / MongoEngine
}

# 同步阻塞函数（模块.函数 或 直接函数名）
BLOCKING_CALLS = {
    "time.sleep",
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.head", "requests.patch", "requests.request",
    "urllib.request.urlopen",
    "subprocess.run", "subprocess.call", "subprocess.check_output",
    "os.system",
    "input",
}

# LLM 性能分析提示词
PERFORMANCE_PROMPT = """你是一个代码性能优化专家。请审查以下代码的性能问题。

代码文件: {file_path}
```
{code_content}
```

请用 JSON 格式返回分析结果，格式如下:
```json
{{
    "findings": [
        {{
            "rule_id": "PERF-001",
            "severity": "critical/warning/suggestion",
            "message": "简短描述性能问题",
            "file_path": "文件路径",
            "line_number": 行号,
            "code_snippet": "问题代码片段",
            "suggestion": "优化建议"
        }}
    ]
}}
```

审查重点:
1. N+1 查询（循环中逐条查询数据库，应批量查询）
2. 全表扫描（缺少 WHERE 条件或索引的数据库查询）
3. 同步阻塞（异步上下文中使用同步 I/O 操作）
4. 低效数据结构（循环内字符串拼接、不必要的列表转换）
5. 内存问题（一次性加载大量数据、无限增长的缓存）
6. 并发瓶颈（锁竞争、串行可并行的操作）

注意:
1. 只返回 JSON，不要有其他内容
2. 如果没有性能问题，返回空数组: {{"findings": []}}
3. severity 分为: critical (严重影响性能), warning (可能影响), suggestion (可优化)
4. 每个问题必须给出具体、可执行的优化建议和优化后代码示例"""


class PerformanceAgent(BaseAgent):
    """性能分析审查 Agent — AST 静态分析 + LLM 语义补充"""

    name = "performance"
    description = "性能分析审查（AST 识别 N+1/全表扫描/同步阻塞 + LLM 优化建议）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行性能分析（AST 静态检测 + LLM 语义分析）"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        findings = []

        # 1. AST 静态分析（确定性工具层；可观测性：记录子步骤）
        import time as _time
        from app.services.review_steps import review_step_recorder

        _t0 = _time.monotonic()
        try:
            ast_findings = self._run_ast_analysis(path, file_paths)
            findings.extend(ast_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="ast_performance",
                    action_text=f"🔍 AST 性能模式检测：命中 {len(ast_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(ast_findings)},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("AST 性能分析失败", error=str(e))

        # 2. LLM 语义分析（补充 AST 漏报的复杂场景）
        try:
            llm_findings = await self._run_llm_analysis(path, file_paths)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM 性能分析失败，回退到 AST 结果", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("性能分析完成", path=project_path, findings=len(unique))
        return unique

    # ──────────────────────────────────────────────────────────────
    # AST 静态分析
    # ──────────────────────────────────────────────────────────────

    def _run_ast_analysis(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """遍历 Python 文件，用 AST 检测性能反模式"""
        findings = []
        py_files = self._collect_python_files(path, file_paths)

        for fp in py_files:
            try:
                source = fp.read_text(errors="ignore")
                tree = ast.parse(source, filename=str(fp))
                rel = str(fp.relative_to(path))

                findings.extend(self._check_n_plus_one(tree, path, rel))
                findings.extend(self._check_sync_in_async(tree, path, rel))
                findings.extend(self._check_string_concat_in_loop(tree, path, rel))
                findings.extend(self._check_unbounded_query(tree, path, rel))
            except SyntaxError:
                continue
            except Exception as e:
                logger.debug("AST 分析跳过文件", file=str(fp), error=str(e))

        return findings

    def _collect_python_files(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[Path]:
        """收集待分析的 Python 文件"""
        if file_paths:
            files = []
            for fp in file_paths:
                full = path / fp
                if full.exists() and full.suffix == ".py":
                    files.append(full)
            return files
        return [
            f for f in path.rglob("*.py")
            if "/__pycache__/" not in str(f)
            and "/node_modules/" not in str(f)
            and "/.venv/" not in str(f)
            and "/venv/" not in str(f)
        ]

    def _check_n_plus_one(
        self,
        tree: ast.AST,
        project_path: Path,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """检测循环内 ORM 调用（N+1 查询反模式）"""
        findings = []

        class _Visitor(ast.NodeVisitor):
            def __init__(self):
                self._loop_depth = 0

            def visit_For(self, node):
                self._loop_depth += 1
                self._scan_body(node.body)
                self.generic_visit(node)
                self._loop_depth -= 1

            def visit_While(self, node):
                self._loop_depth += 1
                self._scan_body(node.body)
                self.generic_visit(node)
                self._loop_depth -= 1

            def visit_ListComp(self, node):
                # 列表推导式内也算循环
                self._loop_depth += 1
                for gen in node.generators:
                    self._scan_expr(gen.iter)
                self.generic_visit(node)
                self._loop_depth -= 1

            def _scan_body(self, stmts):
                if self._loop_depth == 0:
                    return
                for stmt in stmts:
                    self._scan_stmt(stmt)

            def _scan_stmt(self, stmt):
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    self._check_call(stmt.value)
                elif isinstance(stmt, ast.Assign):
                    self._scan_expr(stmt.value)
                elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.value, ast.Call):
                    self._check_call(stmt.value)
                elif isinstance(stmt, ast.Return) and stmt.value:
                    self._scan_expr(stmt.value)
                elif isinstance(stmt, ast.With):
                    for item in stmt.items:
                        self._scan_expr(item.context_expr)

            def _scan_expr(self, expr):
                if isinstance(expr, ast.Call):
                    self._check_call(expr)

            def _check_call(self, call):
                """检查是否为 ORM 调用"""
                method_name = self._get_method_name(call)
                if method_name in ORM_CALL_METHODS:
                    snippet = extract_code_snippet(project_path, file_path, call.lineno)
                    findings.append({
                        "rule_id": "PERF-N+1",
                        "severity": "critical",
                        "message": f"循环内 ORM 调用 `.{method_name}()`（N+1 查询风险），应改为批量查询",
                        "file_path": file_path,
                        "line_start": call.lineno,
                        "code_snippet": snippet[:500],
                        "suggestion": "将循环内的逐条查询改为批量查询（如 `session.query(Model).filter(Model.id.in_(ids)).all()`），减少数据库往返次数",
                    })

            @staticmethod
            def _get_method_name(call):
                if isinstance(call.func, ast.Attribute):
                    return call.func.attr
                if isinstance(call.func, ast.Name):
                    return call.func.id
                return ""

        _Visitor().visit(tree)
        return findings

    def _check_sync_in_async(
        self,
        tree: ast.AST,
        project_path: Path,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """检测 async 函数内的同步阻塞调用"""
        findings = []

        class _AsyncVisitor(ast.NodeVisitor):
            def __init__(self):
                self._in_async = False

            def visit_AsyncFunctionDef(self, node):
                self._in_async = True
                self._scan_body(node.body, node.lineno)
                self.generic_visit(node)
                self._in_async = False

            def _scan_body(self, stmts, func_line):
                if not self._in_async:
                    return
                for stmt in ast.walk(ast.Module(body=stmts, type_ignores=[])):
                    if isinstance(stmt, ast.Call):
                        name = _get_full_name(stmt)
                        if name in BLOCKING_CALLS:
                            snippet = extract_code_snippet(project_path, file_path, stmt.lineno)
                            findings.append({
                                "rule_id": "PERF-SYNC",
                                "severity": "critical",
                                "message": f"async 函数内使用同步阻塞调用 `{name}()`，会阻塞事件循环",
                                "file_path": file_path,
                                "line_start": stmt.lineno,
                                "code_snippet": snippet[:500],
                                "suggestion": f"将 `{name}()` 替换为异步等价物（如 `asyncio.sleep()`、`httpx.AsyncClient`、`asyncio.create_subprocess_exec()`），或用 `asyncio.to_thread()` 包装",
                            })

        def _get_full_name(call):
            """获取调用的完整名称（如 requests.get）"""
            if isinstance(call.func, ast.Attribute):
                parts = []
                node = call.func
                while isinstance(node, ast.Attribute):
                    parts.append(node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    parts.append(node.id)
                return ".".join(reversed(parts))
            if isinstance(call.func, ast.Name):
                return call.func.id
            return ""

        _AsyncVisitor().visit(tree)
        return findings

    def _check_string_concat_in_loop(
        self,
        tree: ast.AST,
        project_path: Path,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """检测循环内字符串 += 拼接（O(n²) 复杂度）"""
        findings = []

        class _ConcatVisitor(ast.NodeVisitor):
            def __init__(self):
                self._loop_depth = 0

            def visit_For(self, node):
                self._loop_depth += 1
                self._scan_body(node.body)
                self.generic_visit(node)
                self._loop_depth -= 1

            def visit_While(self, node):
                self._loop_depth += 1
                self._scan_body(node.body)
                self.generic_visit(node)
                self._loop_depth -= 1

            def _scan_body(self, stmts):
                if self._loop_depth == 0:
                    return
                for stmt in stmts:
                    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.op, ast.Add):
                        if isinstance(stmt.target, ast.Name):
                            snippet = extract_code_snippet(project_path, file_path, stmt.lineno)
                            findings.append({
                                "rule_id": "PERF-CONCAT",
                                "severity": "warning",
                                "message": f"循环内字符串 `+=` 拼接（O(n²) 复杂度），变量 `{stmt.target.id}`",
                                "file_path": file_path,
                                "line_start": stmt.lineno,
                                "code_snippet": snippet[:500],
                                "suggestion": "改用 `''.join(parts)` 或 `io.StringIO` 进行字符串拼接，将复杂度降为 O(n)",
                            })

        _ConcatVisitor().visit(tree)
        return findings

    def _check_unbounded_query(
        self,
        tree: ast.AST,
        project_path: Path,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """检测 .all() 无 .limit() 的无限制查询"""
        findings = []

        class _QueryVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                # 检查 .all() 调用
                if isinstance(node.func, ast.Attribute) and node.func.attr == "all":
                    # 检查调用链中是否有 .limit() 或 [:N]
                    chain = _get_call_chain(node)
                    has_limit = any(m in ("limit", "slice", "take") for m in chain)
                    if not has_limit:
                        snippet = extract_code_snippet(project_path, file_path, node.lineno)
                        findings.append({
                            "rule_id": "PERF-UNBOUNDED",
                            "severity": "suggestion",
                            "message": "无限制查询 `.all()`，未使用 `.limit()` 限制返回数量",
                            "file_path": file_path,
                            "line_start": node.lineno,
                            "code_snippet": snippet[:500],
                            "suggestion": "添加 `.limit(N)` 限制返回数量，避免数据量大时内存溢出或响应过慢",
                        })
                self.generic_visit(node)

        def _get_call_chain(call_node):
            """获取链式调用的方法名列表"""
            chain = []
            node = call_node
            while isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    chain.append(node.func.attr)
                    node = node.func.value
                else:
                    break
            return chain

        _QueryVisitor().visit(tree)
        return findings

    # ──────────────────────────────────────────────────────────────
    # LLM 语义分析
    # ──────────────────────────────────────────────────────────────

    async def _run_llm_analysis(
        self,
        path: Path,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """使用 LLM 进行语义性能分析（注入代码库上下文）"""
        try:
            from app.agents.llm_client import get_active_llm_config, run_llm_analysis
            from app.agents.context_enhancer import agent_context

            config = await get_active_llm_config()
            if not config:
                logger.info("未找到有效的 LLM 配置，跳过 LLM 性能分析")
                return []

            files = collect_code_files_for_llm(path, file_paths)
            if not files:
                return []

            # 构建代码库上下文
            agent_context.build(str(path), file_paths)

            prompts = [
                (
                    fp,
                    agent_context.enhance_prompt(
                        fp,
                        PERFORMANCE_PROMPT.format(file_path=fp, code_content=content),
                    ),
                )
                for fp, content in files
            ]
            findings = await run_llm_analysis(config, prompts, default_rule="LLM-PERF")
            logger.info("LLM 性能分析完成", files=len(files), findings=len(findings))
            return findings

        except ImportError:
            logger.info("LLM 模块不可用，跳过 LLM 性能分析")
            return []

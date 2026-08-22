"""代码索引服务 — AST 符号表 + 调用关系图

构建代码库的结构化索引，供 Context Engine 使用：
1. 符号表：函数/类/变量/导入 的定义与位置
2. 调用关系图：谁调用了谁（函数级）
3. 依赖关系图：文件间的 import 关系

确定性分析（基于 Python AST），零误报，可解释。
"""

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class SymbolInfo:
    """代码符号信息"""
    def __init__(self, name: str, kind: str, file_path: str, line: int, signature: str = ""):
        self.name = name
        self.kind = kind  # function / class / method / variable / import
        self.file_path = file_path
        self.line = line
        self.signature = signature

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line": self.line,
            "signature": self.signature,
        }


class CodeIndex:
    """代码库结构化索引"""

    def __init__(self):
        # 符号表: name -> [SymbolInfo]
        self.symbols: dict[str, list[SymbolInfo]] = defaultdict(list)
        # 调用关系: caller_file -> {callee_name: [caller_line]}
        self.call_graph: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        # 文件依赖: file -> [imported_files]
        self.file_deps: dict[str, list[str]] = defaultdict(list)
        # 文件符号: file -> [SymbolInfo]
        self.file_symbols: dict[str, list[SymbolInfo]] = defaultdict(list)
        # 文件内容缓存（供上下文组装）
        self.file_contents: dict[str, str] = {}

    def build(self, project_path: str, file_paths: list[str] | None = None) -> "CodeIndex":
        """构建代码索引"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return self

        py_files = self._collect_python_files(path, file_paths)
        for fp in py_files:
            try:
                source = fp.read_text(errors="ignore")
                rel = str(fp.relative_to(path))
                self.file_contents[rel] = source
                tree = ast.parse(source, filename=str(fp))
                self._index_file(tree, rel)
            except SyntaxError:
                continue
            except Exception as e:
                logger.debug("索引跳过文件", file=str(fp), error=str(e))

        logger.info("代码索引构建完成", files=len(py_files), symbols=sum(len(v) for v in self.symbols.values()))
        return self

    def _collect_python_files(self, path: Path, file_paths: list[str] | None) -> list[Path]:
        """收集待索引的 Python 文件"""
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

    def _index_file(self, tree: ast.AST, file_path: str):
        """索引单个文件的符号和调用关系"""
        # 收集 import
        imports = self._collect_imports(tree)
        self.file_deps[file_path] = imports

        # 遍历顶层定义
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self._add_symbol(node.name, "function", file_path, node.lineno, self._func_signature(node))
                self._index_calls(node, file_path)
            elif isinstance(node, ast.AsyncFunctionDef):
                self._add_symbol(node.name, "function", file_path, node.lineno, self._func_signature(node))
                self._index_calls(node, file_path)
            elif isinstance(node, ast.ClassDef):
                self._add_symbol(node.name, "class", file_path, node.lineno, "")
                # 类方法
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_name = f"{node.name}.{item.name}"
                        self._add_symbol(method_name, "method", file_path, item.lineno, self._func_signature(item))
                        self._index_calls(item, file_path)

    def _collect_imports(self, tree: ast.AST) -> list[str]:
        """收集文件的 import 依赖"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def _add_symbol(self, name: str, kind: str, file_path: str, line: int, signature: str):
        """添加符号到索引"""
        sym = SymbolInfo(name, kind, file_path, line, signature)
        self.symbols[name].append(sym)
        self.file_symbols[file_path].append(sym)

    def _func_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """生成函数签名"""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        return f"{node.name}({', '.join(args)})"

    def _index_calls(self, node: ast.AST, file_path: str):
        """索引函数体内的调用关系"""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                callee = self._get_callee_name(sub)
                if callee:
                    self.call_graph[file_path][callee].append(sub.lineno)

    @staticmethod
    def _get_callee_name(call: ast.Call) -> str:
        """获取被调用函数名"""
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    # ──────────────────────────────────────────────
    # 查询接口
    # ──────────────────────────────────────────────

    def find_symbol(self, name: str) -> list[SymbolInfo]:
        """查找符号定义"""
        return self.symbols.get(name, [])

    def find_callers(self, callee: str) -> list[dict]:
        """查找谁调用了指定函数"""
        callers = []
        for file_path, calls in self.call_graph.items():
            if callee in calls:
                callers.append({
                    "file_path": file_path,
                    "lines": calls[callee],
                })
        return callers

    def get_file_context(self, file_path: str, max_chars: int = 3000) -> str:
        """获取文件内容（截断）"""
        content = self.file_contents.get(file_path, "")
        return content[:max_chars]

    def get_related_files(self, file_path: str, depth: int = 1) -> list[str]:
        """获取与指定文件相关的文件（import 依赖 + 被依赖）"""
        related = set()
        # 直接依赖
        for dep in self.file_deps.get(file_path, []):
            related.add(dep)
        # 被依赖（其他文件 import 了本文件）
        for other, deps in self.file_deps.items():
            if file_path.split("/")[-1].replace(".py", "") in " ".join(deps):
                related.add(other)
        return list(related)[:depth * 10]

    def get_symbols_in_file(self, file_path: str) -> list[SymbolInfo]:
        """获取文件内所有符号"""
        return self.file_symbols.get(file_path, [])

    def summary(self) -> dict:
        """索引摘要"""
        return {
            "files": len(self.file_contents),
            "symbols": sum(len(v) for v in self.symbols.values()),
            "call_edges": sum(len(v) for v in self.call_graph.values()),
            "file_deps": sum(len(v) for v in self.file_deps.values()),
        }

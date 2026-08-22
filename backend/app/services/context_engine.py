"""上下文引擎 — 组装代码库上下文供 Agent 使用

把 AST 索引（确定性）+ 向量检索（语义）的结果组织成结构化的审查上下文，
让 Agent 在审查单个文件时能理解整个代码库的相关部分。
"""

from pathlib import Path
from typing import Any

import structlog

from app.services.code_index import CodeIndex
from app.services.vector_store import vector_store

logger = structlog.get_logger()


class ContextEngine:
    """代码库上下文引擎"""

    def __init__(self):
        self._index: CodeIndex | None = None
        self._project_path: str | None = None

    def build(self, project_path: str, file_paths: list[str] | None = None) -> "ContextEngine":
        """构建代码库索引"""
        self._project_path = project_path
        self._index = CodeIndex().build(project_path, file_paths)
        # 向量索引（可选，失败降级）
        try:
            vector_store.index_codebase(project_path, file_paths)
        except Exception as e:
            logger.warning("向量索引失败", error=str(e))
        return self

    def get_context(self, file_path: str, query: str | None = None, max_chars: int = 4000) -> dict:
        """获取指定文件的审查上下文

        Args:
            file_path: 被审查的文件
            query: 语义检索查询（可选）
            max_chars: 上下文最大字符数

        Returns:
            { file_content, related_files, symbols, callers, semantic_matches, summary }
        """
        if not self._index:
            return {"file_content": "", "related_files": [], "symbols": [], "callers": [], "semantic_matches": [], "summary": {}}

        # 1. 文件内容
        file_content = self._index.get_file_context(file_path, max_chars)

        # 2. 文件内符号
        symbols = [s.to_dict() for s in self._index.get_symbols_in_file(file_path)]

        # 3. 相关文件（import 依赖）
        related_files = self._index.get_related_files(file_path)

        # 4. 调用者（谁调用了本文件的函数）
        callers = []
        for sym in symbols:
            if sym["kind"] in ("function", "method"):
                callers.extend(self._index.find_callers(sym["name"]))

        # 5. 语义检索（可选）
        semantic_matches = []
        if query:
            try:
                semantic_matches = vector_store.search(query, top_k=3)
            except Exception as e:
                logger.debug("语义检索失败", error=str(e))

        # 6. 相关文件内容（截断）
        related_contents = {}
        for rf in related_files[:5]:
            content = self._index.get_file_context(rf, 1500)
            if content:
                related_contents[rf] = content

        summary = self._index.summary()

        return {
            "file_content": file_content,
            "symbols": symbols,
            "related_files": related_files,
            "related_contents": related_contents,
            "callers": callers,
            "semantic_matches": semantic_matches,
            "summary": summary,
        }

    def build_prompt_context(self, file_path: str, query: str | None = None) -> str:
        """把上下文组装成 prompt 文本（供 Agent 使用）"""
        ctx = self.get_context(file_path, query)
        parts = []

        # 文件内容
        if ctx["file_content"]:
            parts.append(f"## 被审查文件: {file_path}\n```\n{ctx['file_content']}\n```")

        # 相关文件
        if ctx["related_contents"]:
            parts.append("## 相关文件（import 依赖）:")
            for rf, content in ctx["related_contents"].items():
                parts.append(f"### {rf}\n```\n{content}\n```")

        # 符号
        if ctx["symbols"]:
            sym_lines = [f"- {s['kind']} {s['signature'] or s['name']} (line {s['line']})" for s in ctx["symbols"][:20]]
            parts.append("## 文件内符号:\n" + "\n".join(sym_lines))

        # 调用者
        if ctx["callers"]:
            caller_lines = [f"- {c['file_path']} (lines {c['lines'][:5]})" for c in ctx["callers"][:10]]
            parts.append("## 调用本文件函数的位置:\n" + "\n".join(caller_lines))

        # 语义匹配
        if ctx["semantic_matches"]:
            parts.append("## 语义相关代码:")
            for m in ctx["semantic_matches"]:
                parts.append(f"### {m['file']}:{m.get('line', '')} (score {m.get('score', 0)})\n```\n{m['content'][:800]}\n```")

        return "\n\n".join(parts)


# 全局单例
context_engine = ContextEngine()

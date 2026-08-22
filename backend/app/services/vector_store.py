"""向量化检索服务 — 语义代码检索

基于代码块 Embedding 的语义检索，补充 AST 确定性索引无法覆盖的语义理解。
使用轻量本地方案（可选），若未安装依赖则优雅降级为关键词检索。
"""

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# 尝试导入向量库（可选依赖）
try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

try:
    import chromadb
    _HAS_CHROMA = True
except ImportError:
    _HAS_CHROMA = False


class VectorStore:
    """轻量向量检索（语义代码检索）"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = None
        self._model_name = model_name
        self._chunks: list[dict] = []  # [{id, file, content, embedding}]
        self._ready = False

    def is_available(self) -> bool:
        """向量检索是否可用"""
        return _HAS_ST

    def _ensure_model(self):
        """懒加载 Embedding 模型"""
        if self._model is None and _HAS_ST:
            try:
                self._model = SentenceTransformer(self._model_name)
                self._ready = True
                logger.info("Embedding 模型加载完成", model=self._model_name)
            except Exception as e:
                logger.warning("Embedding 模型加载失败，降级为关键词检索", error=str(e))
                self._ready = False

    def index_codebase(self, project_path: str, file_paths: list[str] | None = None):
        """索引代码库（分块 + Embedding）"""
        if not _HAS_ST:
            logger.info("未安装 sentence-transformers，跳过向量索引")
            return

        self._ensure_model()
        if not self._ready:
            return

        path = Path(project_path)
        if not path.exists():
            return

        py_files = self._collect_python_files(path, file_paths)
        self._chunks = []

        for fp in py_files:
            try:
                source = fp.read_text(errors="ignore")
                rel = str(fp.relative_to(path))
                # 按函数/类分块
                chunks = self._chunk_code(source, rel)
                for chunk in chunks:
                    emb = self._model.encode(chunk["content"]).tolist()
                    chunk["embedding"] = emb
                    self._chunks.append(chunk)
            except Exception as e:
                logger.debug("向量索引跳过文件", file=str(fp), error=str(e))

        logger.info("向量索引完成", chunks=len(self._chunks))

    def _collect_python_files(self, path: Path, file_paths: list[str] | None) -> list[Path]:
        """收集 Python 文件"""
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

    def _chunk_code(self, source: str, file_path: str) -> list[dict]:
        """把代码按函数/类分块"""
        import ast

        chunks = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", node.lineno)
                    lines = source.splitlines()
                    content = "\n".join(lines[start:end])
                    if content.strip():
                        chunks.append({
                            "id": f"{file_path}:{node.lineno}",
                            "file": file_path,
                            "content": content[:2000],
                            "name": node.name,
                            "line": node.lineno,
                        })
        except SyntaxError:
            pass
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索相关代码块"""
        if not self._ready or not self._chunks:
            # 降级：关键词检索
            return self._keyword_search(query, top_k)

        self._ensure_model()
        if not self._ready:
            return self._keyword_search(query, top_k)

        try:
            query_emb = self._model.encode(query)
            scored = []
            for chunk in self._chunks:
                emb = chunk["embedding"]
                score = self._cosine_sim(query_emb, emb)
                scored.append((score, chunk))
            scored.sort(key=lambda x: -x[0])
            return [
                {**chunk, "score": round(score, 3)}
                for score, chunk in scored[:top_k]
            ]
        except Exception as e:
            logger.warning("向量检索失败，降级为关键词检索", error=str(e))
            return self._keyword_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        """关键词检索（降级方案）"""
        keywords = set(re.findall(r"[a-zA-Z_]\w*", query.lower()))
        scored = []
        for chunk in self._chunks:
            content_lower = chunk["content"].lower()
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [
            {**chunk, "score": round(score, 3)}
            for score, chunk in scored[:top_k]
        ]

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


# 全局单例
vector_store = VectorStore()

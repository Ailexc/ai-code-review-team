"""Agent 上下文增强 — 为 LLM 分析注入代码库上下文

在 Agent 调用 LLM 分析前，用 Context Engine 构建代码库索引，
为每个被审查文件补充相关文件、符号、调用者、语义匹配等上下文。
"""

from pathlib import Path
from typing import Any

import structlog

from app.services.context_engine import ContextEngine

logger = structlog.get_logger()


class AgentContextEnhancer:
    """为 Agent 的 LLM 分析注入代码库上下文"""

    def __init__(self):
        self._engine: ContextEngine | None = None
        self._project_path: str | None = None

    def build(self, project_path: str, file_paths: list[str] | None = None) -> "AgentContextEnhancer":
        """构建代码库上下文索引"""
        self._project_path = project_path
        try:
            self._engine = ContextEngine().build(project_path, file_paths)
        except Exception as e:
            logger.warning("上下文引擎构建失败，降级为无上下文", error=str(e))
            self._engine = None
        return self

    def enhance_prompt(self, file_path: str, base_prompt: str) -> str:
        """把代码库上下文注入到基础 prompt 中"""
        if not self._engine:
            return base_prompt

        try:
            context_text = self._engine.build_prompt_context(file_path)
            if not context_text:
                return base_prompt

            # 在基础 prompt 前注入代码库上下文
            return (
                "以下是代码库上下文（帮助理解被审查文件在整个项目中的位置）：\n\n"
                f"{context_text}\n\n"
                "---\n\n"
                f"{base_prompt}"
            )
        except Exception as e:
            logger.debug("上下文注入失败", error=str(e))
            return base_prompt


# 全局单例
agent_context = AgentContextEnhancer()

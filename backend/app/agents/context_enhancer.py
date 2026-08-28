"""Agent 上下文增强 — 为 LLM 分析注入代码库上下文（并发安全版）

设计（2026-08-25 重构，修复并行竞态）：
- 旧版：全局单例 agent_context 持有可变状态（_engine/_project_path），
  6 个 Crew 并行执行时各自 build() 互相覆盖 —— 多项目并行审查会数据串味，
  且同一项目索引被重复构建 6 次。
- 新版：
  1. 引擎实例按 (project_path, file_paths) 缓存复用（dict 原子赋值，无锁；
     极端并发下最多重复构建一次，正确性不受影响），full 审查 6 个 Crew 共享一份索引；
  2. 当前引擎经 ContextVar 随审查上下文传递（由 ReviewFlow._run_crew_node 设置，
     与 current_review_ctx 同生命周期），enhance_prompt 无状态读取 —— 并行隔离；
  3. 不在审查链路中（无上下文）时 enhance_prompt 原样返回，优雅降级。
"""

import contextvars

import structlog

from app.services.context_engine import ContextEngine

logger = structlog.get_logger()

# 当前审查的代码库上下文引擎（ReviewFlow 在 kickoff 前 set，工具链路内读取）
current_context_engine: contextvars.ContextVar[ContextEngine | None] = contextvars.ContextVar(
    "current_context_engine", default=None
)

# 引擎缓存：(project_path, file_paths元组) -> ContextEngine（仅缓存成功构建）
# 上限防内存增长：超出后清空最旧的一半（简单策略，学习项目足够）
_ENGINE_CACHE: dict[tuple, ContextEngine] = {}
_ENGINE_CACHE_MAX = 8


def get_or_build_engine(project_path: str, file_paths: list[str] | None = None) -> ContextEngine | None:
    """获取（或构建并缓存）项目上下文引擎

    并行 Crew 对同一项目共享同一实例；构建失败返回 None（不缓存失败，
    下次调用重试）。线程安全性依赖 GIL 的 dict 原子操作，无锁。
    """
    key = (str(project_path), tuple(sorted(file_paths or [])))
    engine = _ENGINE_CACHE.get(key)
    if engine is not None:
        return engine
    try:
        engine = ContextEngine().build(project_path, file_paths)
    except Exception as e:
        logger.warning("上下文引擎构建失败", error=str(e), project=project_path)
        return None
    if len(_ENGINE_CACHE) >= _ENGINE_CACHE_MAX:
        # 简单淘汰：清空一半（dict 保序，前面的最旧）
        for old_key in list(_ENGINE_CACHE.keys())[: _ENGINE_CACHE_MAX // 2]:
            _ENGINE_CACHE.pop(old_key, None)
    _ENGINE_CACHE[key] = engine
    return engine


def set_current_engine(engine: ContextEngine | None):
    """设置当前审查的引擎（返回 token 供 reset）"""
    return current_context_engine.set(engine)


def reset_current_engine(token) -> None:
    """恢复引擎上下文（配对 set_current_engine 使用）"""
    current_context_engine.reset(token)


def enhance_prompt(file_path: str, base_prompt: str) -> str:
    """把代码库上下文注入到基础 prompt 中（无状态；从 ContextVar 读当前引擎）

    不在审查链路中或引擎未就绪时，原样返回 base_prompt（优雅降级）。
    """
    engine = current_context_engine.get()
    if not engine:
        return base_prompt
    try:
        context_text = engine.build_prompt_context(file_path)
        if not context_text:
            return base_prompt
        return (
            "以下是代码库上下文（帮助理解被审查文件在整个项目中的位置）：\n\n"
            f"{context_text}\n\n"
            "---\n\n"
            f"{base_prompt}"
        )
    except Exception as e:
        logger.debug("上下文注入失败", error=str(e))
        return base_prompt


def clear_engine_cache() -> None:
    """清空引擎缓存（测试用）"""
    _ENGINE_CACHE.clear()

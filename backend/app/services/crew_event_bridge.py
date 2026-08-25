"""CrewAI 事件桥接器 — 把框架事件总线广播的细粒度事件转为可观测性步骤

CrewAI 1.6.1 在执行过程中会通过 crewai_event_bus 广播 LLM 调用 / 工具使用 /
Crew 启动结束等事件（字段含完整提示词、工具参数、输出、精确耗时）。
本模块注册同步监听器，把事件翻译为中文步骤意图（intent）放入线程安全队列，
由主事件循环上的常驻排空器批量落库（review_steps + llm_call_logs 全文档案）。

为什么用「队列 + 排空器」而不是在处理器里直接写库：
- CrewAI 的同步处理器运行在自己的线程池（无事件循环），异步处理器运行在
  框架私有的后台循环——两者都不适合复用主应用的 SQLAlchemy 异步引擎
  （连接池绑定事件循环，跨循环使用会报 "attached to a different loop"）。
- 队列方案让所有 DB 写入都留在主循环，处理器本身零阻塞、零异常外泄。

并行归属：_run_crew_node 在 kickoff 前 bind(review_id, agent_name) 建立
角色 → 上下文映射；CrewKickoffStartedEvent 再把 crew 内 agent_id 补进映射。
LLM/Tool 事件按 from_agent.id → agent_id → role 的顺序反查归属。

任何处理失败只打日志，绝不影响审查主流程。
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any

import structlog

from app.services.review_steps import review_step_recorder, _truncate

logger = structlog.get_logger()

# ============ 归属注册表（线程安全：dict 操作原子；bind 在主循环写，处理器在读） ============

_ctx_by_role: dict[str, dict[str, str]] = {}      # agent role → {review_id, agent_name, role}
_ctx_by_agent_id: dict[str, dict[str, str]] = {}  # crewai agent id → ctx

# 处理器线程 → 排空器的意图队列
_intent_queue: queue.Queue[dict[str, Any]] = queue.Queue()

# 每个 ctx 的模型调用计数与进行中调用（单 Agent Crew 内串行，per-ctx 即可）
_llm_seq: dict[str, int] = {}
_pending_llm: dict[str, dict[str, Any]] = {}
_pending_tool: dict[str, dict[str, Any]] = {}

_drainer_task: asyncio.Task | None = None
_registered = False


def bind(review_id: str, agent_name: str) -> None:
    """登记一次内层 Crew 执行的归属（kickoff 前在主循环调用）"""
    if not review_id or not agent_name:
        return
    from app.flows.crew_factory import AGENT_PROFILES

    role = AGENT_PROFILES.get(agent_name, {}).get("role", agent_name)
    ctx = {"review_id": review_id, "agent_name": agent_name, "role": role}
    _ctx_by_role[role] = ctx


def _ctx_key(ctx: dict[str, str]) -> str:
    return f"{ctx['review_id']}:{ctx['agent_name']}"


def _resolve_ctx(event: Any) -> dict[str, str] | None:
    """从事件反查归属上下文：from_agent.id → agent_id → from_agent.role → agent_role"""
    candidates: list[tuple[str, str | None]] = []
    fa = getattr(event, "from_agent", None)
    if fa is not None:
        candidates.append(("id", getattr(fa, "id", None)))
        candidates.append(("role", getattr(fa, "role", None)))
    candidates.append(("id", getattr(event, "agent_id", None)))
    candidates.append(("role", getattr(event, "agent_role", None)))

    for kind, value in candidates:
        if not value:
            continue
        if kind == "id" and value in _ctx_by_agent_id:
            return _ctx_by_agent_id[value]
        if kind == "role" and value in _ctx_by_role:
            return _ctx_by_role[value]
    return None


def resolve(agent_id: str | None = None, role: str | None = None) -> dict[str, str] | None:
    """按 agent_id / role 反查归属上下文（CorrelationStore 协议公开方法）"""
    if agent_id and agent_id in _ctx_by_agent_id:
        return _ctx_by_agent_id[agent_id]
    if role and role in _ctx_by_role:
        return _ctx_by_role[role]
    return None


def cleanup(review_id: str) -> None:
    """清理指定审查的全部归属映射（CorrelationStore 协议公开方法）"""
    global _ctx_by_agent_id, _ctx_by_role
    _ctx_by_agent_id = {k: v for k, v in _ctx_by_agent_id.items() if v["review_id"] != review_id}
    _ctx_by_role = {k: v for k, v in _ctx_by_role.items() if v["review_id"] != review_id}


# ============ 字段提取工具 ============


def _extract_text(value: Any) -> str:
    """尽力把事件里的 response/output 提取为文本"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for attr in ("raw", "content", "text"):
        v = getattr(value, attr, None)
        if isinstance(v, str) and v:
            return v
    msg = getattr(value, "message", None)
    if msg is not None:
        inner = getattr(msg, "content", None)
        if isinstance(inner, str) and inner:
            return inner
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _extract_usage(response_text_or_obj: Any) -> dict[str, int]:
    """尽力从响应对象提取 token 用量（litellm Usage 挂在响应上时）"""
    usage = getattr(response_text_or_obj, "usage", None) if not isinstance(response_text_or_obj, str) else None
    if usage is None:
        return {}
    def _i(k: str) -> int:
        try:
            return int(getattr(usage, k, 0) or 0)
        except Exception:
            return 0
    return {
        "prompt_tokens": _i("prompt_tokens"),
        "completion_tokens": _i("completion_tokens"),
        "total_tokens": _i("total_tokens"),
    }


def _normalize_messages(messages: Any) -> list[dict[str, str]]:
    """把事件的 messages（str 或 list[dict]）规整为可存储结构"""
    if messages is None:
        return []
    if isinstance(messages, str):
        return [{"role": "raw", "content": messages}]
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append({"role": str(m.get("role", "?")), "content": str(m.get("content", ""))})
        else:
            content = getattr(m, "content", None)
            role = getattr(m, "role", None)
            out.append({"role": str(role or "?"), "content": str(content or m)})
    return out


def _count_findings(output_text: str) -> int | None:
    """工具输出若为 findings JSON 则统计条数"""
    if not output_text:
        return None
    try:
        data = json.loads(output_text)
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return len(data["findings"])
    except Exception:
        pass
    return None


def _ts_diff_ms(start: datetime | None, end: datetime | None) -> int:
    if not start or not end:
        return 0
    try:
        return max(0, int((end - start).total_seconds() * 1000))
    except Exception:
        return 0


# ============ 事件处理器（同步，运行在 CrewAI 线程池；只入队不落库） ============


def _on_crew_kickoff_started(source: Any, event: Any) -> None:
    try:
        crew_name = getattr(event, "crew_name", "") or ""
        ctx: dict[str, str] | None = None
        if ":" in crew_name:
            rid, agent = crew_name.split(":", 1)
            # bind() 已建过则复用；否则兜底建立（crew_name 格式 "{review_id}:{agent_name}"）
            ctx = next(
                (c for c in _ctx_by_role.values()
                 if c["review_id"] == rid and c["agent_name"] == agent),
                None,
            ) or {"review_id": rid, "agent_name": agent, "role": agent}
        # 用 crew 对象内的 agent 精确映射（并行多审查时 role 可能被覆盖，id 唯一）
        crew = getattr(event, "crew", None)
        if crew is not None and ctx is not None:
            for a in getattr(crew, "agents", None) or []:
                aid = getattr(a, "id", None)
                if aid:
                    _ctx_by_agent_id[aid] = ctx
    except Exception as e:
        logger.warning("crew_event_bridge: kickoff_started 处理失败", error=str(e))


def _on_crew_kickoff_finished(source: Any, event: Any) -> None:
    try:
        # 清理该 crew 的 agent_id 映射（防长期累积）；role 映射留给下次 bind 覆盖
        crew = getattr(event, "crew", None)
        if crew is not None:
            for a in getattr(crew, "agents", None) or []:
                aid = getattr(a, "id", None)
                if aid:
                    _ctx_by_agent_id.pop(aid, None)
        _pending_llm.clear()
        _pending_tool.clear()
    except Exception as e:
        logger.warning("crew_event_bridge: kickoff_finished 处理失败", error=str(e))


def _on_llm_started(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        _llm_seq[key] = _llm_seq.get(key, 0) + 1
        _pending_llm[key] = {
            "seq_no": _llm_seq[key],
            "model": getattr(event, "model", None),
            "messages": _normalize_messages(getattr(event, "messages", None)),
            "ts": getattr(event, "timestamp", None),
        }
    except Exception as e:
        logger.warning("crew_event_bridge: llm_started 处理失败", error=str(e))


def _on_llm_completed(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        pending = _pending_llm.pop(key, {})
        call_type_enum = getattr(event, "call_type", None)
        call_type = getattr(call_type_enum, "value", None) or str(call_type_enum or "llm_call")
        response_obj = getattr(event, "response", None)
        response_text = _extract_text(response_obj)
        latency_ms = _ts_diff_ms(pending.get("ts"), getattr(event, "timestamp", None))
        _intent_queue.put({
            "kind": "crewai_llm",
            "fields": {
                "review_id": ctx["review_id"],
                "agent_name": ctx["agent_name"],
                "call_type": call_type,
                "model": pending.get("model") or getattr(event, "model", None),
                "messages": pending.get("messages") or [],
                "response_text": response_text,
                "latency_ms": latency_ms,
                "usage": _extract_usage(response_obj),
                "success": True,
                "seq_no": pending.get("seq_no", 0),
            },
        })
    except Exception as e:
        logger.warning("crew_event_bridge: llm_completed 处理失败", error=str(e))


def _on_llm_failed(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        pending = _pending_llm.pop(key, {})
        _intent_queue.put({
            "kind": "crewai_llm",
            "fields": {
                "review_id": ctx["review_id"],
                "agent_name": ctx["agent_name"],
                "call_type": "llm_call",
                "model": pending.get("model") or getattr(event, "model", None),
                "messages": pending.get("messages") or [],
                "response_text": "",
                "latency_ms": _ts_diff_ms(pending.get("ts"), getattr(event, "timestamp", None)),
                "usage": {},
                "success": False,
                "error": _truncate(_extract_text(getattr(event, "error", None)) or "未知错误", 300),
                "seq_no": pending.get("seq_no", 0),
            },
        })
    except Exception as e:
        logger.warning("crew_event_bridge: llm_failed 处理失败", error=str(e))


def _on_tool_started(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        args = getattr(event, "tool_args", None)
        if not isinstance(args, dict):
            args = {"raw": str(args)}
        _pending_tool[key] = {
            "tool_name": getattr(event, "tool_name", ""),
            "tool_args": args,
        }
    except Exception as e:
        logger.warning("crew_event_bridge: tool_started 处理失败", error=str(e))


def _on_tool_finished(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        pending = _pending_tool.pop(key, {})
        tool_name = pending.get("tool_name") or getattr(event, "tool_name", "")
        output_text = _extract_text(getattr(event, "output", None))
        duration_ms = _ts_diff_ms(
            getattr(event, "started_at", None), getattr(event, "finished_at", None)
        )
        findings = _count_findings(output_text)
        findings_part = f"，产出 {findings} 条发现" if findings is not None else ""
        cache_part = "（命中缓存）" if getattr(event, "from_cache", False) else ""
        _intent_queue.put({
            "kind": "step",
            "emit": True,
            "fields": {
                "review_id": ctx["review_id"],
                "phase": "tool",
                "node_type": "tool_call",
                "status": "completed",
                "agent_name": ctx["agent_name"],
                "action_text": f"🔧 工具 {tool_name} 执行完成{findings_part}（{duration_ms / 1000:.1f}s）{cache_part}",
                "input_summary": f"参数：{_truncate(json.dumps(pending.get('tool_args', {}), ensure_ascii=False), 150)}",
                "output_summary": f"{findings} 条发现" if findings is not None else _truncate(output_text, 150),
                "duration_ms": duration_ms,
                "detail": {
                    "tool_name": tool_name,
                    "tool_args": pending.get("tool_args", {}),
                    "from_cache": bool(getattr(event, "from_cache", False)),
                    "findings": findings,
                    "output_preview": _truncate(output_text, 300),
                },
            },
        })
    except Exception as e:
        logger.warning("crew_event_bridge: tool_finished 处理失败", error=str(e))


def _on_tool_error(source: Any, event: Any) -> None:
    try:
        ctx = _resolve_ctx(event)
        if not ctx:
            return
        key = _ctx_key(ctx)
        pending = _pending_tool.pop(key, {})
        tool_name = pending.get("tool_name") or getattr(event, "tool_name", "")
        _intent_queue.put({
            "kind": "step",
            "emit": True,
            "fields": {
                "review_id": ctx["review_id"],
                "phase": "tool",
                "node_type": "tool_call",
                "status": "failed",
                "agent_name": ctx["agent_name"],
                "action_text": f"⚠️ 工具 {tool_name} 执行失败：{_truncate(_extract_text(getattr(event, 'error', None)), 120)}",
                "input_summary": f"参数：{_truncate(json.dumps(pending.get('tool_args', {}), ensure_ascii=False), 150)}",
                "duration_ms": None,
                "detail": {"tool_name": tool_name, "tool_args": pending.get("tool_args", {})},
            },
        })
    except Exception as e:
        logger.warning("crew_event_bridge: tool_error 处理失败", error=str(e))


# ============ 注册与排空器 ============


def register_crew_event_bridge() -> None:
    """向 CrewAI 事件总线注册全局监听器并启动排空器（幂等；应用启动时调用一次）"""
    global _registered, _drainer_task
    if _registered:
        return
    _registered = True

    from crewai.events import (
        LLMCallCompletedEvent,
        LLMCallFailedEvent,
        LLMCallStartedEvent,
        ToolUsageErrorEvent,
        ToolUsageFinishedEvent,
        ToolUsageStartedEvent,
        CrewKickoffCompletedEvent,
        CrewKickoffFailedEvent,
        CrewKickoffStartedEvent,
        crewai_event_bus,
    )

    crewai_event_bus.register_handler(CrewKickoffStartedEvent, _on_crew_kickoff_started)
    crewai_event_bus.register_handler(CrewKickoffCompletedEvent, _on_crew_kickoff_finished)
    crewai_event_bus.register_handler(CrewKickoffFailedEvent, _on_crew_kickoff_finished)
    crewai_event_bus.register_handler(LLMCallStartedEvent, _on_llm_started)
    crewai_event_bus.register_handler(LLMCallCompletedEvent, _on_llm_completed)
    crewai_event_bus.register_handler(LLMCallFailedEvent, _on_llm_failed)
    crewai_event_bus.register_handler(ToolUsageStartedEvent, _on_tool_started)
    crewai_event_bus.register_handler(ToolUsageFinishedEvent, _on_tool_finished)
    crewai_event_bus.register_handler(ToolUsageErrorEvent, _on_tool_error)

    _drainer_task = asyncio.get_running_loop().create_task(_drain_loop())
    logger.info("crew_event_bridge: 事件桥接器已注册")


async def shutdown_crew_event_bridge() -> None:
    """停止排空器（应用关闭时调用）"""
    global _drainer_task
    if _drainer_task is not None:
        _drainer_task.cancel()
        _drainer_task = None


async def _drain_loop() -> None:
    """常驻排空：批量取队列意图并在主循环落库（所有 DB 写入都在主循环）"""
    while True:
        try:
            await asyncio.sleep(0.1)
            batch: list[dict[str, Any]] = []
            while not _intent_queue.empty():
                try:
                    batch.append(_intent_queue.get_nowait())
                except queue.Empty:
                    break
            for intent in batch:
                try:
                    await _persist(intent)
                except Exception as e:
                    logger.warning("crew_event_bridge: 意图落库失败", error=str(e))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("crew_event_bridge: 排空循环异常", error=str(e))


async def _persist(intent: dict[str, Any]) -> None:
    if intent["kind"] == "step":
        fields = intent["fields"]
        await review_step_recorder.record(**fields)
        if intent.get("emit"):
            from app.services.progress import progress_emitter

            await progress_emitter.emit(
                fields["review_id"],
                f"step_{fields['node_type']}",
                {"agent": fields.get("agent_name"), "text": fields.get("action_text")},
            )
    elif intent["kind"] == "crewai_llm":
        await review_step_recorder.record_crewai_llm_call(**intent["fields"])

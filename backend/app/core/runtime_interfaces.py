"""运行时组件协议接口 — 为水平扩展预留的对接点（2026-08-25）

当前系统为单进程部署，以下三个组件是进程内存态实现：
1. ProgressEmitter   （app/services/progress.py）      —— WS 实时事件总线
2. CrewEventBridge   （app/services/crew_event_bridge.py）—— 框架事件归属映射表
3. MetricsTracker    （app/services/metrics.py）        —— 运行时指标聚合

它们都遵循本模块声明的 Protocol。未来若需多 worker / 多机部署，
按协议提供 Redis / Postgres 等分布式实现并替换注入即可，业务层无需改动：

    组件                 协议                  分布式替换方案（示例）
    ─────────────────────────────────────────────────────────────────
    progress_emitter     EventPublisher       Redis Pub/Sub + WS 网关
    crew_event_bridge    CorrelationStore     Redis Hash（TTL = 审查时长）
    metrics              MetricsStore         Prometheus client / StatsD

设计约束（各实现必须遵守）：
- 所有方法异步安全，允许从任意线程调用（桥接器处理器运行在框架线程池）；
- 任何失败不得向调用方抛异常（可观测性永不阻断审查主流程）；
- CorrelationStore 的键空间随审查结束清理，防长期累积。
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """实时事件发布/订阅协议（当前实现：progress_emitter）"""

    async def emit(self, review_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        """向指定审查的事件流发布一条消息"""
        ...

    def subscribe(self, review_id: str) -> Any:
        """订阅审查事件流，返回队列句柄"""
        ...

    def unsubscribe(self, review_id: str, queue: Any) -> None:
        """取消订阅"""
        ...


@runtime_checkable
class CorrelationStore(Protocol):
    """事件归属关联存储协议（当前实现：crew_event_bridge 内部注册表）"""

    def bind(self, review_id: str, agent_name: str) -> None:
        """登记一次内层执行的归属映射"""
        ...

    def resolve(self, agent_id: str | None = None, role: str | None = None) -> dict[str, str] | None:
        """按 agent_id / role 反查归属上下文 {review_id, agent_name}"""
        ...

    def cleanup(self, review_id: str) -> None:
        """清理指定审查的全部映射（审查结束时调用）"""
        ...


@runtime_checkable
class MetricsStore(Protocol):
    """运行时指标存储协议（当前实现：metrics 内存聚合器）"""

    def record_review(self, review_type: str, status: str, duration_s: float) -> None: ...
    def record_llm_call(self, success: bool, latency_s: float, tokens: int = 0, model: str = "") -> None: ...
    def record_agent_run(self, agent_name: str, success: bool, duration_s: float, findings_count: int = 0) -> None: ...
    def snapshot(self) -> dict[str, Any]:
        """返回指标快照（供 /system/metrics 端点）"""
        ...

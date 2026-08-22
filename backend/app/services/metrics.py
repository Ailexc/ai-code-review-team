"""运行时指标收集 — 内存级 Review / LLM / Agent 执行指标 + 审计日志

提供 /system/metrics 端点数据源，展示审查耗时、LLM 调用统计、Agent 成功率等。
纯内存实现（重启归零），真实持久数据从数据库聚合（见 system.py /metrics 端点）。"""

import time
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger()


class MetricsTracker:
    """全局运行时指标收集器"""

    def __init__(self):
        self._reviews_total: int = 0
        self._reviews_by_type: dict[str, int] = defaultdict(int)
        self._reviews_by_status: dict[str, int] = defaultdict(int)
        self._review_durations: dict[str, list[float]] = defaultdict(list)

        self._llm_calls_total: int = 0
        self._llm_calls_success: int = 0
        self._llm_calls_failed: int = 0
        self._llm_total_tokens: int = 0
        self._llm_latencies: list[float] = []
        # 按模型 token 统计
        self._llm_tokens_by_model: dict[str, int] = defaultdict(int)

        self._agent_runs: dict[str, int] = defaultdict(int)
        self._agent_successes: dict[str, int] = defaultdict(int)
        self._agent_failures: dict[str, int] = defaultdict(int)
        self._agent_durations: dict[str, list[float]] = defaultdict(list)
        self._agent_findings: dict[str, int] = defaultdict(int)

        # 审计日志（最近 100 条）
        self._audit_log: list[dict] = []

        self._start_time = time.monotonic()

    def reset(self) -> None:
        """重置所有指标（仅用于测试）"""
        self.__init__()

    # — Review —

    def record_review(self, review_type: str, status: str, duration_s: float) -> None:
        """记录一次审查完成"""
        self._reviews_total += 1
        self._reviews_by_type[review_type] += 1
        self._reviews_by_status[status] += 1
        self._review_durations[review_type].append(duration_s)
        logger.debug("metrics:review_recorded", review_type=review_type, status=status, duration=duration_s)

    # — LLM —

    def record_llm_call(self, success: bool, latency_s: float, tokens: int = 0, model: str = "") -> None:
        """记录一次 LLM 调用（含 token 统计）"""
        self._llm_calls_total += 1
        if success:
            self._llm_calls_success += 1
        else:
            self._llm_calls_failed += 1
        self._llm_total_tokens += tokens
        self._llm_latencies.append(latency_s)

        # 按模型 token 统计
        if model:
            self._llm_tokens_by_model[model] += tokens

    # — 审计日志 —

    def record_audit(self, action: str, detail: dict | None = None) -> None:
        """记录审计日志（审查操作历史）"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "detail": detail or {},
        }
        self._audit_log.append(entry)
        # 只保留最近 100 条
        if len(self._audit_log) > 100:
            self._audit_log = self._audit_log[-100:]

    # — Agent —

    def record_agent_run(self, agent_name: str, success: bool, duration_s: float, findings_count: int = 0) -> None:
        """记录一次 Agent 执行"""
        self._agent_runs[agent_name] += 1
        if success:
            self._agent_successes[agent_name] += 1
        else:
            self._agent_failures[agent_name] += 1
        self._agent_durations[agent_name].append(duration_s)
        self._agent_findings[agent_name] += findings_count

    # — Query —

    def snapshot(self) -> dict[str, Any]:
        """返回当前指标快照"""
        def _avg(xs: list[float]) -> float:
            return round(sum(xs) / len(xs), 2) if xs else 0.0

        def _p95(xs: list[float]) -> float:
            if not xs:
                return 0.0
            s = sorted(xs)
            idx = int(len(s) * 0.95)
            return round(s[min(idx, len(s) - 1)], 2)

        agents: dict[str, dict] = {}
        for name in set(list(self._agent_runs.keys()) + list(self._agent_successes.keys())):
            runs = self._agent_runs.get(name, 0)
            successes = self._agent_successes.get(name, 0)
            agents[name] = {
                "runs": runs,
                "successes": successes,
                "failures": self._agent_failures.get(name, 0),
                "success_rate": round(successes / runs, 3) if runs else 0,
                "avg_duration_s": _avg(self._agent_durations.get(name, [])),
                "p95_duration_s": _p95(self._agent_durations.get(name, [])),
                "total_findings": self._agent_findings.get(name, 0),
            }

        return {
            "reviews": {
                "total": self._reviews_total,
                "by_type": dict(self._reviews_by_type),
                "by_status": dict(self._reviews_by_status),
                "avg_duration_s": {
                    t: _avg(ds) for t, ds in self._review_durations.items()
                },
            },
            "llm": {
                "calls_total": self._llm_calls_total,
                "calls_success": self._llm_calls_success,
                "calls_failed": self._llm_calls_failed,
                "success_rate": round(self._llm_calls_success / self._llm_calls_total, 3) if self._llm_calls_total else 0,
                "total_tokens": self._llm_total_tokens,
                "avg_latency_s": _avg(self._llm_latencies),
                "p95_latency_s": _p95(self._llm_latencies),
                "tokens_by_model": dict(self._llm_tokens_by_model),
            },
            "agents": agents,
            "audit_log": list(self._audit_log),
        }


# 全局单例
metrics = MetricsTracker()
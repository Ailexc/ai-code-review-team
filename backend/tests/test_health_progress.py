"""健康度评分 + 进度事件总线测试"""

import asyncio

import pytest

from app.services.health import compute_health_score, health_score_color
from app.services.progress import ProgressEmitter


class FakeReview:
    def __init__(self, critical=0, warning=0, suggestion=0, nitpick=0):
        self.critical_count = critical
        self.warning_count = warning
        self.suggestion_count = suggestion
        self.nitpick_count = nitpick
        self.total_findings = critical + warning + suggestion + nitpick


class FakeFinding:
    def __init__(self, severity):
        self.severity = severity


def test_health_score_clean():
    r = FakeReview()
    assert compute_health_score(r) == 100.0


def test_health_score_with_critical():
    r = FakeReview(critical=2, warning=1)
    # 100 - 30 - 5 = 65
    assert compute_health_score(r) == 65.0


def test_health_score_clamped_to_zero():
    r = FakeReview(critical=10)
    assert compute_health_score(r) == 0.0


def test_health_score_with_findings_list():
    findings = [FakeFinding("critical"), FakeFinding("warning"), FakeFinding("suggestion"), FakeFinding("nitpick")]
    r = FakeReview()
    # 100 - 15 - 5 - 2 - 0.5 = 77.5
    assert compute_health_score(r, findings) == 77.5


def test_health_score_color():
    assert health_score_color(90) == "green"
    assert health_score_color(70) == "orange"
    assert health_score_color(50) == "gold"
    assert health_score_color(20) == "red"


@pytest.mark.asyncio
async def test_progress_emitter_pubsub():
    emitter = ProgressEmitter()
    q = emitter.subscribe("rev-1")
    await emitter.emit("rev-1", "test_event", {"key": "value"})
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["event"] == "test_event"
    assert msg["review_id"] == "rev-1"
    assert msg["data"]["key"] == "value"


@pytest.mark.asyncio
async def test_progress_emitter_unsubscribe():
    emitter = ProgressEmitter()
    q = emitter.subscribe("rev-2")
    emitter.unsubscribe("rev-2", q)
    assert "rev-2" not in emitter._subscribers


@pytest.mark.asyncio
async def test_progress_emitter_no_subs_no_error():
    emitter = ProgressEmitter()
    # 没有订阅者时发布不应报错
    await emitter.emit("rev-3", "orphan_event")


@pytest.mark.asyncio
async def test_progress_emitter_replays_history():
    """订阅前发射的事件应在订阅时回放"""
    emitter = ProgressEmitter()
    # 无订阅者时发射事件
    await emitter.emit("rev-4", "review_started", {"project": "x"})
    await emitter.emit("rev-4", "agent_started", {"agent": "security"})
    # 现在订阅
    q = emitter.subscribe("rev-4")
    # 应立即收到 2 条历史事件
    msg1 = await asyncio.wait_for(q.get(), timeout=1.0)
    msg2 = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg1["event"] == "review_started"
    assert msg2["event"] == "agent_started"
    assert msg2["data"]["agent"] == "security"

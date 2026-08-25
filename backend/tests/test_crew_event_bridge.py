"""CrewAI 事件桥接器单元测试 — 验证事件 → 步骤意图的转换与归属解析

不依赖数据库：处理器只做字段提取/归属解析并入队，测试直接检查队列内容。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import crew_event_bridge as bridge


@pytest.fixture(autouse=True)
def _reset_bridge_state():
    """每个用例重置桥接器内部状态，避免串扰"""
    bridge._ctx_by_role.clear()
    bridge._ctx_by_agent_id.clear()
    bridge._llm_seq.clear()
    bridge._pending_llm.clear()
    bridge._pending_tool.clear()
    # 清空队列
    while not bridge._intent_queue.empty():
        bridge._intent_queue.get_nowait()
    yield
    bridge._ctx_by_role.clear()
    bridge._ctx_by_agent_id.clear()
    bridge._llm_seq.clear()
    bridge._pending_llm.clear()
    bridge._pending_tool.clear()
    while not bridge._intent_queue.empty():
        bridge._intent_queue.get_nowait()


def _drain_intents() -> list[dict]:
    out = []
    while not bridge._intent_queue.empty():
        out.append(bridge._intent_queue.get_nowait())
    return out


class TestBind:
    def test_bind_registers_role_mapping(self):
        bridge.bind("rev-1", "security")
        assert "资深代码安全审查专家" in bridge._ctx_by_role
        ctx = bridge._ctx_by_role["资深代码安全审查专家"]
        assert ctx["review_id"] == "rev-1"
        assert ctx["agent_name"] == "security"

    def test_bind_ignores_empty(self):
        bridge.bind("", "security")
        bridge.bind("rev-1", "")
        assert not bridge._ctx_by_role


class TestResolveCtx:
    def test_resolve_via_agent_id(self):
        bridge.bind("rev-1", "security")
        agent = SimpleNamespace(id="agent-xyz", role="资深代码安全审查专家")
        event = SimpleNamespace(from_agent=agent, agent_id=None, agent_role=None)
        ctx = bridge._resolve_ctx(event)
        assert ctx is not None
        assert ctx["review_id"] == "rev-1"

    def test_resolve_via_role_fallback(self):
        bridge.bind("rev-2", "performance")
        event = SimpleNamespace(
            from_agent=None, agent_id=None, agent_role="性能分析专家"
        )
        ctx = bridge._resolve_ctx(event)
        assert ctx is not None
        assert ctx["agent_name"] == "performance"

    def test_resolve_unknown_returns_none(self):
        event = SimpleNamespace(
            from_agent=None, agent_id="ghost", agent_role="幽灵角色"
        )
        assert bridge._resolve_ctx(event) is None


class TestLLMEvents:
    def test_llm_started_completed_produces_intent(self):
        bridge.bind("rev-1", "security")
        agent = SimpleNamespace(id="a1", role="资深代码安全审查专家")

        t0 = datetime.now(timezone.utc)
        started = SimpleNamespace(
            from_agent=agent, agent_id="a1", agent_role="资深代码安全审查专家",
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你是安全专家"}, {"role": "user", "content": "扫描"}],
            timestamp=t0,
        )
        bridge._on_llm_started(None, started)

        completed = SimpleNamespace(
            from_agent=agent, agent_id="a1", agent_role="资深代码安全审查专家",
            model="deepseek-chat",
            response=SimpleNamespace(content='{"tool": "scan"}'),
            call_type=SimpleNamespace(value="tool_call"),
            timestamp=t0 + timedelta(seconds=3),
        )
        bridge._on_llm_completed(None, completed)

        intents = _drain_intents()
        assert len(intents) == 1
        fields = intents[0]["fields"]
        assert intents[0]["kind"] == "crewai_llm"
        assert fields["review_id"] == "rev-1"
        assert fields["agent_name"] == "security"
        assert fields["call_type"] == "tool_call"
        assert fields["seq_no"] == 1
        assert fields["latency_ms"] == 3000
        assert len(fields["messages"]) == 2
        assert fields["response_text"] == '{"tool": "scan"}'

    def test_llm_failed_produces_failed_intent(self):
        bridge.bind("rev-1", "security")
        agent = SimpleNamespace(id="a1", role="资深代码安全审查专家")
        t0 = datetime.now(timezone.utc)
        bridge._on_llm_started(None, SimpleNamespace(
            from_agent=agent, model="m",
            messages=[], timestamp=t0,
        ))
        bridge._on_llm_failed(None, SimpleNamespace(
            from_agent=agent, model="m",
            error="timeout", timestamp=t0 + timedelta(seconds=1),
        ))
        intents = _drain_intents()
        assert len(intents) == 1
        assert intents[0]["fields"]["success"] is False
        assert "timeout" in intents[0]["fields"]["error"]

    def test_unbound_event_dropped(self):
        agent = SimpleNamespace(id="nobody", role="无名氏")
        bridge._on_llm_completed(None, SimpleNamespace(
            from_agent=agent, response="x",
            call_type=SimpleNamespace(value="llm_call"),
            timestamp=datetime.now(timezone.utc),
        ))
        assert _drain_intents() == []


class TestToolEvents:
    def test_tool_finished_counts_findings(self):
        bridge.bind("rev-9", "code_style")
        agent = SimpleNamespace(id="a2", role="代码规范审查专家")
        started_at = datetime.now(timezone.utc)
        finished_at = started_at + timedelta(seconds=5)

        bridge._on_tool_started(None, SimpleNamespace(
            from_agent=agent, tool_name="code_style_review_scan",
            tool_args={"path": ""},
        ))
        bridge._on_tool_finished(None, SimpleNamespace(
            from_agent=agent, tool_name="code_style_review_scan",
            output='{"findings": [{}, {}, {}]}',
            started_at=started_at, finished_at=finished_at, from_cache=False,
        ))

        intents = _drain_intents()
        assert len(intents) == 1
        f = intents[0]["fields"]
        assert intents[0]["kind"] == "step"
        assert f["phase"] == "tool"
        assert f["node_type"] == "tool_call"
        assert f["agent_name"] == "code_style"
        assert f["duration_ms"] == 5000
        assert f["detail"]["findings"] == 3
        assert "3 条发现" in f["action_text"]

    def test_tool_error(self):
        bridge.bind("rev-9", "git_review")
        agent = SimpleNamespace(id="a3", role="Git 变更审查专家")
        bridge._on_tool_started(None, SimpleNamespace(
            from_agent=agent, tool_name="git_review_scan", tool_args={},
        ))
        bridge._on_tool_error(None, SimpleNamespace(
            from_agent=agent, tool_name="git_review_scan", error="boom",
        ))
        intents = _drain_intents()
        assert intents[0]["fields"]["status"] == "failed"


class TestKickoffMapping:
    def test_kickoff_started_maps_agent_ids(self):
        crew = SimpleNamespace(agents=[SimpleNamespace(id="ag-1"), SimpleNamespace(id="ag-2")])
        event = SimpleNamespace(crew_name="rev-77:dependency", crew=crew)
        bridge._on_crew_kickoff_started(None, event)
        assert bridge._ctx_by_agent_id["ag-1"]["review_id"] == "rev-77"
        assert bridge._ctx_by_agent_id["ag-1"]["agent_name"] == "dependency"

        # 后续 LLM 事件凭 agent_id 即可归属（无需 bind）
        bridge._on_llm_started(None, SimpleNamespace(
            from_agent=SimpleNamespace(id="ag-1", role="依赖安全审查专家"),
            model="m", messages=[], timestamp=datetime.now(timezone.utc),
        ))
        bridge._on_llm_completed(None, SimpleNamespace(
            from_agent=SimpleNamespace(id="ag-1", role="依赖安全审查专家"),
            response="ok", call_type=SimpleNamespace(value="llm_call"),
            timestamp=datetime.now(timezone.utc),
        ))
        intents = _drain_intents()
        assert intents[0]["fields"]["review_id"] == "rev-77"

    def test_kickoff_finished_cleans_agent_ids(self):
        crew = SimpleNamespace(agents=[SimpleNamespace(id="ag-9")])
        bridge._on_crew_kickoff_started(None, SimpleNamespace(crew_name="r:git_review", crew=crew))
        assert "ag-9" in bridge._ctx_by_agent_id
        bridge._on_crew_kickoff_finished(None, SimpleNamespace(crew=crew))
        assert "ag-9" not in bridge._ctx_by_agent_id


class TestHelpers:
    def test_extract_text_variants(self):
        assert bridge._extract_text("plain") == "plain"
        assert bridge._extract_text(SimpleNamespace(raw="raw-text")) == "raw-text"
        assert bridge._extract_text(None) == ""

    def test_normalize_messages_str(self):
        msgs = bridge._normalize_messages("single string prompt")
        assert msgs == [{"role": "raw", "content": "single string prompt"}]

    def test_count_findings(self):
        assert bridge._count_findings('{"findings": [1, 2]}') == 2
        assert bridge._count_findings("not json") is None

    def test_ts_diff(self):
        a = datetime.now(timezone.utc)
        b = a + timedelta(milliseconds=1500)
        assert bridge._ts_diff_ms(a, b) == 1500
        assert bridge._ts_diff_ms(None, b) == 0

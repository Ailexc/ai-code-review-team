"""ReviewFlow（CrewAI Flows 外层编排）集成测试

验证外层 Flow 的编排逻辑：节点流转、6 个内层 Crew 并行分派、review_type 过滤、
聚合去重。Crew 构建与 LLM 通过 mock（工具/LLM 真实调用由 test_crew_factory 覆盖）。
"""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, patch

SECURITY_FINDINGS = [
    {"rule_id": "F-SEC-1", "severity": "critical", "message": "SQL注入", "file_path": "a.py", "line_start": 5, "code_snippet": "x", "suggestion": "s"},
]
STYLE_FINDINGS = [
    {"rule_id": "F-STYLE-1", "severity": "nitpick", "message": "import 未排序", "file_path": "a.py", "line_start": 1, "code_snippet": "y", "suggestion": "s"},
]
DEP_FINDINGS = [
    {"rule_id": "F-DEP-1", "severity": "warning", "message": "依赖漏洞", "file_path": "requirements.txt", "line_start": 1},
]


class FakeCrewResult:
    """模拟 Crew kickoff 返回（raw JSON 走解析兜底）"""

    def __init__(self, findings: list[dict]):
        self.pydantic = None
        self.raw = json.dumps({"findings": findings}, ensure_ascii=False)


class FakeCrew:
    def __init__(self, findings: list[dict]):
        self.findings = findings

    async def kickoff_async(self, **kwargs):
        return FakeCrewResult(self.findings)


def _patch_flow(agent_findings: dict[str, list[dict]]):
    """把 build_review_crew 替换为按 agent_name 返回固定 findings 的 FakeCrew"""
    def fake_build(agent_name, project_path, file_paths, llm, crew_name=None):
        return FakeCrew(agent_findings.get(agent_name, []))

    return (
        patch("app.flows.review_flow.build_review_crew", side_effect=fake_build),
        patch.object(ReviewFlow, "_get_llm", new=AsyncMock(return_value=object())),
    )


from app.flows.review_flow import ReviewFlow, run_review_flow


@pytest.mark.asyncio
async def test_review_flow_full_runs_all_crews(tmp_path):
    """full 类型应通过 Flow 并行编排运行 6 个内层 Crew 并聚合"""
    (tmp_path / "a.py").write_text("x = 1\n")

    findings = {"security": SECURITY_FINDINGS, "code_style": STYLE_FINDINGS}
    p1, p2 = _patch_flow(findings)
    with p1, p2:
        state = await run_review_flow(
            project_path=str(tmp_path),
            review_type="full",
            project_name="flow-test",
        )

    # 6 个 Agent 全部参与（即使部分无 findings）
    assert set(state.findings_by_agent.keys()) == {
        "security", "code_style", "dependency",
        "test_coverage", "performance", "git_review",
    }
    assert state.findings_by_agent["security"][0]["rule_id"] == "F-SEC-1"
    assert state.findings_by_agent["security"][0]["severity"] == "critical"
    assert state.findings_by_agent["code_style"][0]["message"] == "import 未排序"
    assert state.total_findings == 2
    assert "发现" in state.summary


@pytest.mark.asyncio
async def test_review_flow_single_type(tmp_path):
    """单类型只运行对应 Crew"""
    (tmp_path / "a.py").write_text("x = 1\n")

    p1, p2 = _patch_flow({"security": SECURITY_FINDINGS})
    with p1, p2:
        state = await run_review_flow(
            project_path=str(tmp_path),
            review_type="security",
        )
    assert state.findings_by_agent.keys() == {"security"}


@pytest.mark.asyncio
async def test_review_flow_dedup(tmp_path):
    """两个 Agent 报告同一位置同一规则 → 聚合去重"""
    (tmp_path / "a.py").write_text("x = 1\n")
    dup = [{"rule_id": "DUP", "severity": "warning", "message": "m", "file_path": "a.py", "line_start": 1}]

    p1, p2 = _patch_flow({"security": dup, "code_style": dup})
    with p1, p2:
        state = await run_review_flow(project_path=str(tmp_path), review_type="full")

    assert state.total_findings == 1  # 去重后


@pytest.mark.asyncio
async def test_review_flow_unknown_type_falls_back_to_security(tmp_path):
    """未知审查类型回退 security"""
    (tmp_path / "a.py").write_text("x = 1\n")

    p1, p2 = _patch_flow({"security": SECURITY_FINDINGS})
    with p1, p2:
        state = await run_review_flow(project_path=str(tmp_path), review_type="whatever")

    assert state.findings_by_agent.keys() == {"security"}


@pytest.mark.asyncio
async def test_review_flow_emits_progress_events(tmp_path):
    """带 review_id 时发布 flow_node_*/agent_* 进度事件"""
    from app.services.progress import progress_emitter

    (tmp_path / "a.py").write_text("x = 1\n")
    queue = progress_emitter.subscribe("flow-test-events")

    try:
        p1, p2 = _patch_flow({"security": SECURITY_FINDINGS})
        with p1, p2:
            state = await run_review_flow(
                project_path=str(tmp_path),
                review_type="security",
                review_id="flow-test-events",
            )

        # 收集事件（非阻塞读，事件已入队）
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()["event"])

        assert "flow_node_started" in events
        assert "flow_node_completed" in events
        assert "agent_started" in events
        assert "agent_completed" in events
    finally:
        progress_emitter.unsubscribe("flow-test-events", queue)

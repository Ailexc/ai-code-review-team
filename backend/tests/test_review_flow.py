"""ReviewFlow（CrewAI Flows 双层编排骨架）集成测试

Agent 执行通过 mock，避免真实 semgrep/LLM 调用，专注验证 Flow 编排逻辑。
"""

import asyncio

import pytest
from unittest.mock import patch


SECURITY_FINDINGS = [
    {"rule_id": "F-SEC-1", "severity": "critical", "message": "SQL注入", "file_path": "a.py", "line_start": 5, "code_snippet": "x", "suggestion": "s"},
]
STYLE_FINDINGS = [
    {"rule_id": "F-STYLE-1", "severity": "nitpick", "message": "import 未排序", "file_path": "a.py", "line_start": 1, "code_snippet": "y", "suggestion": "s"},
]


class FakeSecurityAgent:
    async def analyze(self, project_path, file_paths=None):
        return SECURITY_FINDINGS


class FakeStyleAgent:
    async def analyze(self, project_path, file_paths=None):
        return STYLE_FINDINGS


@pytest.mark.asyncio
async def test_review_flow_full_orchestrates_both_agents(tmp_path):
    """full 类型应通过 Flow 编排并行运行两个 Agent 并聚合去重"""
    (tmp_path / "a.py").write_text("x = 1\n")

    from app.flows.review_flow import run_review_flow, _AGENT_MAP

    fake_map = {
        "security": (FakeSecurityAgent, "security", "security"),
        "code_style": (FakeStyleAgent, "code_style", "code_style"),
    }
    with patch("app.flows.review_flow._AGENT_MAP", fake_map):
        state = await run_review_flow(
            project_path=str(tmp_path),
            review_type="full",
            project_name="flow-test",
        )

    assert state.total_findings == 2
    assert set(state.findings_by_agent.keys()) == {"security", "code_style"}
    assert "发现" in state.summary


@pytest.mark.asyncio
async def test_review_flow_single_type(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")

    from app.flows.review_flow import run_review_flow

    fake_map = {
        "security": (FakeSecurityAgent, "security", "security"),
        "code_style": (FakeStyleAgent, "code_style", "code_style"),
    }
    with patch("app.flows.review_flow._AGENT_MAP", fake_map):
        state = await run_review_flow(
            project_path=str(tmp_path),
            review_type="security",
        )
    assert state.total_findings == 1
    assert "security" in state.findings_by_agent


@pytest.mark.asyncio
async def test_review_flow_dedup(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")

    # 两个 Agent 报告同一位置同一规则 → 去重
    class DupA:
        async def analyze(self, project_path, file_paths=None):
            return [{"rule_id": "DUP", "severity": "warning", "message": "m", "file_path": "a.py", "line_start": 1}]

    class DupB:
        async def analyze(self, project_path, file_paths=None):
            return [{"rule_id": "DUP", "severity": "warning", "message": "m", "file_path": "a.py", "line_start": 1}]

    fake_map = {
        "security": (DupA, "security", "security"),
        "code_style": (DupB, "code_style", "code_style"),
    }
    with patch("app.flows.review_flow._AGENT_MAP", fake_map):
        from app.flows.review_flow import run_review_flow
        state = await run_review_flow(project_path=str(tmp_path), review_type="full")

    assert state.total_findings == 1  # 去重后

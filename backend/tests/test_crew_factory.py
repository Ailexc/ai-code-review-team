"""内层 Crew 工厂（crew_factory）测试

验证：CrewAI LLM 构建、Crew 结构（Agent/Task/Crew）、工具封装、
结果解析（output_pydantic 与 raw 兜底）、无 LLM 配置时的清晰报错。
"""

import json

import pytest
from unittest.mock import AsyncMock, patch

from app.flows.crew_factory import (
    AGENT_PROFILES,
    FindingsOutput,
    build_crew_llm,
    build_review_crew,
    parse_crew_findings,
)


class FakeLLMConfig:
    model = "gpt-4o"
    base_url = "https://example.com/v1"
    api_key = "sk-test"
    temperature = 0.3


@pytest.fixture
def llm():
    return build_crew_llm(FakeLLMConfig())


def test_build_crew_llm_uses_project_config():
    """build_crew_llm 应使用项目 LLM 配置（base_url/api_key/model）"""
    llm = build_crew_llm(FakeLLMConfig())
    assert llm is not None
    assert llm.model == FakeLLMConfig.model


def test_agent_profiles_cover_six_agents():
    """AGENT_PROFILES 应覆盖 6 个专业 Agent，且都有中文角色/目标/背景"""
    assert set(AGENT_PROFILES.keys()) == {
        "security", "code_style", "dependency",
        "test_coverage", "performance", "git_review",
    }
    for name, profile in AGENT_PROFILES.items():
        assert profile["role"], name
        assert profile["goal"], name
        assert profile["backstory"], name


def test_build_review_crew_structure(tmp_path, llm):
    """build_review_crew 应产出标准 Crew：1 Agent + 1 Task + 工具"""
    crew = build_review_crew("security", str(tmp_path), None, llm)

    assert crew is not None
    assert len(crew.agents) == 1
    assert len(crew.tasks) == 1
    agent = crew.agents[0]
    task = crew.tasks[0]
    # Agent 有角色与工具
    assert "安全" in agent.role
    assert len(agent.tools) == 1
    # Task 有描述与期望输出
    assert "security_review_scan" in task.description or "扫描" in task.description
    assert task.expected_output
    assert task.output_pydantic is not None


def test_build_review_crew_unknown_agent(tmp_path, llm):
    """未知 agent_name 应抛 KeyError（由 AGENT_REGISTRY 层过滤）"""
    with pytest.raises(KeyError):
        build_review_crew("unknown_agent", str(tmp_path), None, llm)


def test_parse_crew_findings_pydantic_output():
    """output_pydantic 结构解析"""
    from app.flows.crew_factory import FindingItem

    out = FindingsOutput(findings=[FindingItem(rule_id="P-1", severity="critical")])

    class R:
        pydantic = out
        raw = ""

    result = parse_crew_findings(R())
    assert result[0]["rule_id"] == "P-1"
    assert result[0]["severity"] == "critical"


def test_parse_crew_findings_raw_json():
    """raw JSON 兜底解析"""

    class R:
        pydantic = None
        raw = json.dumps({"findings": [
            {"rule_id": "X-1", "severity": "warning", "message": "m", "file_path": "a.py", "line_start": 3},
        ]})

    result = parse_crew_findings(R())
    assert result[0]["rule_id"] == "X-1"
    assert result[0]["severity"] == "warning"
    assert result[0]["line_start"] == 3


@pytest.mark.asyncio
async def test_review_flow_requires_llm_config(tmp_path):
    """无 LLM 配置时 run_review_flow 应抛出清晰错误（不静默降级）"""
    from app.flows.review_flow import run_review_flow

    (tmp_path / "a.py").write_text("x = 1\n")
    with patch("app.flows.review_flow.get_active_llm_config", AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError, match="LLM"):
            await run_review_flow(project_path=str(tmp_path), review_type="security")

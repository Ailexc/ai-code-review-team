"""测试共享工具 — patch CrewAI 编排层，避免真实 LLM / 工具调用

重构后审查主路径 = ReviewFlow（CrewAI Flows + Crews）→ 内层 build_review_crew()。
测试通过 patch_review_flow() 替换：
- build_review_crew → 按 agent_name 返回固定 findings 的 FakeCrew（走真实 Flow 编排，
  验证节点流转/聚合/入库，不触发真实 CrewAI LLM 工具调用）
- get_active_llm_config → 假配置（Flow 预检通过）

用法：
    p = patch_review_flow({"security": SECURITY_FINDINGS})
    with p:
        await client.post("/api/v1/reviews/run", ...)
"""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch


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


class FakeLLMConfig:
    model = "test-model"
    base_url = "https://example.com/v1"
    api_key = "sk-test"
    temperature = 0.2


def patch_review_flow(agent_findings: dict[str, list[dict]]):
    """patch Flow 编排层：build_review_crew 按 agent 返回固定 findings + 假 LLM 配置

    返回 ExitStack（支持 with），同时生效多个 patch。
    用法：
        with patch_review_flow({"security": SECURITY_FINDINGS}):
            await client.post("/api/v1/reviews/run", ...)
    """
    def fake_build(agent_name, project_path, file_paths, llm, crew_name=None):
        return FakeCrew(agent_findings.get(agent_name, []))

    stack = ExitStack()
    stack.enter_context(patch("app.flows.review_flow.build_review_crew", side_effect=fake_build))
    stack.enter_context(
        patch(
            "app.flows.review_flow.get_active_llm_config",
            new=AsyncMock(return_value=FakeLLMConfig()),
        )
    )
    return stack

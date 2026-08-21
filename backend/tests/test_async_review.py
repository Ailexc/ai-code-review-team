"""异步审查（run-async + 轮询）集成测试"""

import asyncio

import pytest
from unittest.mock import patch


def _sample_project():
    return {"name": "异步审查项目", "language": "python", "path": "/tmp/async-review-project"}


@pytest.mark.asyncio
async def test_run_async_returns_running_then_completes(client):
    """run-async 应立即返回 running，后台完成后可轮询到 completed"""
    project_id = (await client.post("/api/v1/projects", json=_sample_project())).json()["id"]

    class FakeAgent:
        async def analyze(self, project_path, file_paths=None):
            await asyncio.sleep(0.05)  # 模拟耗时
            return [{"rule_id": "ASYNC-1", "severity": "warning", "message": "异步测试发现", "file_path": "a.py", "line_start": 1}]

    # patch 需覆盖整个轮询过程，确保后台任务也使用 mock Agent
    with patch.dict(
        "app.services.review_service.AGENT_REGISTRY",
        {"security": (FakeAgent, "security", "security")},
    ):
        resp = await client.post(
            "/api/v1/reviews/run-async",
            params={"project_id": project_id, "review_type": "security"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "running"
        review_id = data["id"]

        # 轮询直到完成（后台任务）
        for _ in range(50):
            await asyncio.sleep(0.1)
            r = await client.get(f"/api/v1/reviews/{review_id}")
            d = r.json()
            if d["status"] in ("completed", "failed"):
                break

        final = (await client.get(f"/api/v1/reviews/{review_id}")).json()
    assert final["status"] == "completed"
    assert final["total_findings"] == 1
    assert final["health_score_snapshot"] is not None
    assert 0 <= final["health_score_snapshot"] <= 100

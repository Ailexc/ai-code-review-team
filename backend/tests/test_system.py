"""系统 API 集成测试"""

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "docs" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_stats_empty(client):
    resp = await client.get("/api/v1/system/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["projects_total"] == 0
    assert data["reviews_total"] == 0
    assert data["findings_total"] == 0


@pytest.mark.asyncio
async def test_stats_with_data(client):
    await client.post("/api/v1/projects", json={
        "name": "统计项目", "language": "python", "path": "/tmp/stats-project",
    })
    project = (await client.get("/api/v1/projects")).json()["items"][0]

    class FakeAgent:
        async def analyze(self, project_path, file_paths=None):
            return [
                {"severity": "critical", "message": "c1", "file_path": "a.py", "line_start": 1},
                {"severity": "warning", "message": "w1", "file_path": "b.py", "line_start": 1},
            ]

    with patch.dict(
        "app.services.review_service.AGENT_REGISTRY",
        {"security": (FakeAgent, "security", "security")},
    ):
        await client.post("/api/v1/reviews/run", params={"project_id": project["id"]})

    resp = await client.get("/api/v1/system/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["projects_total"] == 1
    assert data["reviews_total"] == 1
    assert data["findings_total"] == 2
    assert data["findings_critical"] == 1
    assert data["findings_warning"] == 1
    assert len(data["recent_reviews"]) == 1

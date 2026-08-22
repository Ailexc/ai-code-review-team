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
    # V8.0: 新增字段
    assert "findings_acknowledged" in data
    assert "findings_status_distribution" in data
    assert data["findings_status_distribution"]["open"] >= 0
    assert "review_trends" in data
    assert isinstance(data["review_trends"], list)
    # recent_reviews 应含 health_score_snapshot
    assert "health_score_snapshot" in data["recent_reviews"][0]


@pytest.mark.asyncio
async def test_metrics_empty(client):
    """空数据库时 metrics 端点应返回初始状态"""
    resp = await client.get("/api/v1/system/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reviews"]["total"] == 0
    assert data["findings"]["total"] == 0
    assert data["llm"]["calls_total"] == 0
    assert data["llm"]["total_tokens"] == 0


@pytest.mark.asyncio
async def test_metrics_after_review(client):
    """执行审查后 metrics 应记录 review + findings 指标"""
    await client.post("/api/v1/projects", json={
        "name": "Metrics 测试", "language": "python", "path": "/tmp/metrics-test",
    })
    project = (await client.get("/api/v1/projects")).json()["items"][0]

    class FakeAgent:
        async def analyze(self, project_path, file_paths=None):
            return [{"severity": "warning", "message": "w1", "file_path": "a.py", "line_start": 1}]

    with patch.dict(
        "app.services.review_service.AGENT_REGISTRY",
        {"security": (FakeAgent, "security", "security")},
    ):
        await client.post("/api/v1/reviews/run", params={"project_id": project["id"], "review_type": "security"})

    resp = await client.get("/api/v1/system/metrics")
    assert resp.status_code == 200
    data = resp.json()

    # 审查指标
    assert data["reviews"]["total"] == 1
    assert data["reviews"]["completed"] == 1
    assert data["reviews"]["by_type"]["security"] == 1

    # findings 指标
    assert data["findings"]["total"] == 1
    assert data["findings"]["by_severity"]["warning"] == 1
    assert data["findings"]["by_agent"]["security"] == 1

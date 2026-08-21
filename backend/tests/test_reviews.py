"""审查流程 API 集成测试（Agent 分析通过 mock，避免真实 semgrep/LLM 调用）"""

import pytest
from unittest.mock import patch


def _sample_project():
    return {
        "name": "审查测试项目",
        "language": "python",
        "path": "/tmp/review-test-project",
    }


async def _create_project(client):
    resp = await client.post("/api/v1/projects", json=_sample_project())
    return resp.json()["id"]


# mock 的安全审查结果
FAKE_FINDINGS = [
    {
        "rule_id": "TEST-001",
        "severity": "critical",
        "message": "发现 SQL 注入风险",
        "file_path": "app/main.py",
        "line_start": 10,
        "line_end": 10,
        "code_snippet": "query = f\"SELECT * FROM users WHERE id={uid}\"",
        "suggestion": "使用参数化查询",
    },
    {
        "rule_id": "TEST-002",
        "severity": "warning",
        "message": "使用了 eval",
        "file_path": "app/main.py",
        "line_start": 20,
        "code_snippet": "eval(user_input)",
        "suggestion": "避免使用 eval",
    },
]


class FakeAgent:
    async def analyze(self, project_path, file_paths=None):
        return FAKE_FINDINGS


@pytest.mark.asyncio
async def test_create_review_record(client):
    project_id = await _create_project(client)
    resp = await client.post("/api/v1/reviews", json={
        "project_id": project_id,
        "review_type": "security",
        "trigger_type": "manual",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["review_type"] == "security"


@pytest.mark.asyncio
async def test_create_review_project_not_found(client):
    resp = await client.post("/api/v1/reviews", json={
        "project_id": "nonexistent",
        "review_type": "security",
        "trigger_type": "manual",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_review_completed(client):
    project_id = await _create_project(client)
    with patch("app.services.review_service.SecurityAgent", FakeAgent):
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "security"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["total_findings"] == 2
    assert data["critical_count"] == 1
    assert data["warning_count"] == 1
    assert data["summary"]


@pytest.mark.asyncio
async def test_run_review_project_not_found(client):
    resp = await client.post("/api/v1/reviews/run", params={"project_id": "nonexistent"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_reviews(client):
    project_id = await _create_project(client)
    with patch("app.services.review_service.SecurityAgent", FakeAgent):
        await client.post("/api/v1/reviews/run", params={"project_id": project_id})
    resp = await client.get("/api/v1/reviews")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_review_with_findings(client):
    project_id = await _create_project(client)
    with patch("app.services.review_service.SecurityAgent", FakeAgent):
        created = (await client.post(
            "/api/v1/reviews/run", params={"project_id": project_id}
        )).json()

    resp = await client.get(f"/api/v1/reviews/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 2


@pytest.mark.asyncio
async def test_download_report(client):
    project_id = await _create_project(client)
    with patch("app.services.review_service.SecurityAgent", FakeAgent):
        created = (await client.post(
            "/api/v1/reviews/run", params={"project_id": project_id}
        )).json()

    resp = await client.get(f"/api/v1/reviews/{created['id']}/report")
    assert resp.status_code == 200
    assert "# 代码审查报告" in resp.text
    assert "SQL 注入风险" in resp.text
    assert resp.headers["content-type"].startswith("text/markdown")


@pytest.mark.asyncio
async def test_findings_listing(client):
    project_id = await _create_project(client)
    with patch("app.services.review_service.SecurityAgent", FakeAgent):
        created = (await client.post(
            "/api/v1/reviews/run", params={"project_id": project_id}
        )).json()

    resp = await client.get(f"/api/v1/findings", params={"review_id": created["id"]})
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings) == 2
    assert findings[0]["severity"] in ("critical", "warning", "suggestion")

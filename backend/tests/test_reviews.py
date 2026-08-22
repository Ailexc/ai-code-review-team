"""审查流程 API 集成测试（CrewAI 编排层通过 mock，避免真实 LLM/工具调用）"""

import pytest
from unittest.mock import patch

from helpers import patch_review_flow


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
SECURITY_FINDINGS = [
    {
        "rule_id": "TEST-SEC-001",
        "severity": "critical",
        "message": "发现 SQL 注入风险",
        "file_path": "app/main.py",
        "line_start": 10,
        "line_end": 10,
        "code_snippet": 'query = f"SELECT * FROM users WHERE id={uid}"',
        "suggestion": "使用参数化查询",
    },
    {
        "rule_id": "TEST-SEC-002",
        "severity": "warning",
        "message": "使用了 eval",
        "file_path": "app/main.py",
        "line_start": 20,
        "code_snippet": "eval(user_input)",
        "suggestion": "避免使用 eval",
    },
]

# mock 的规范审查结果
STYLE_FINDINGS = [
    {
        "rule_id": "TEST-STYLE-001",
        "severity": "suggestion",
        "message": "函数命名不规范",
        "file_path": "app/main.py",
        "line_start": 30,
        "code_snippet": "def badname():",
        "suggestion": "改为更清晰的名称",
        "is_auto_fixable": False,
    },
    {
        "rule_id": "TEST-STYLE-002",
        "severity": "nitpick",
        "message": "import 未排序",
        "file_path": "app/main.py",
        "line_start": 1,
        "code_snippet": "import os\nimport sys",
        "suggestion": "ruff 可自动修复",
        "is_auto_fixable": True,
    },
]


def _patch_security():
    return patch_review_flow({"security": SECURITY_FINDINGS})


def _patch_all():
    return patch_review_flow({
        "security": SECURITY_FINDINGS,
        "code_style": STYLE_FINDINGS,
    })


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
async def test_run_security_review(client):
    project_id = await _create_project(client)
    with _patch_security():
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "security"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["review_type"] == "security"
    assert data["total_findings"] == 2
    assert data["critical_count"] == 1
    assert data["warning_count"] == 1


@pytest.mark.asyncio
async def test_run_code_style_review(client):
    project_id = await _create_project(client)
    with _patch_all():
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "code_style"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["review_type"] == "code_style"
    assert data["total_findings"] == 2
    assert data["suggestion_count"] == 1
    assert data["nitpick_count"] == 1


@pytest.mark.asyncio
async def test_run_full_review_runs_both_agents(client):
    """full 类型应并行运行 security + code_style 两个 Agent"""
    project_id = await _create_project(client)
    with _patch_all():
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "full"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["review_type"] == "full"
    assert data["total_findings"] == 4  # 2 security + 2 code_style


@pytest.mark.asyncio
async def test_run_dependency_review(client):
    project_id = await _create_project(client)

    with patch_review_flow({"dependency": [{"rule_id": "DEP-1", "severity": "warning", "message": "requests 过时", "file_path": "requirements.txt", "line_start": 1}]}):
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "dependency"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["review_type"] == "dependency"
    assert data["total_findings"] == 1


@pytest.mark.asyncio
async def test_run_test_coverage_review(client):
    project_id = await _create_project(client)

    with patch_review_flow({"test_coverage": [{"rule_id": "TEST-1", "severity": "suggestion", "message": "函数未测试", "file_path": "app.py", "line_start": 5}]}):
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "test_coverage"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["review_type"] == "test_coverage"
    assert data["total_findings"] == 1


@pytest.mark.asyncio
async def test_run_review_project_not_found(client):
    resp = await client.post("/api/v1/reviews/run", params={"project_id": "nonexistent"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_reviews(client):
    project_id = await _create_project(client)
    with _patch_security():
        await client.post("/api/v1/reviews/run", params={"project_id": project_id})
    resp = await client.get("/api/v1/reviews")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_download_report(client):
    project_id = await _create_project(client)
    with _patch_all():
        created = (await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "full"},
        )).json()

    resp = await client.get(f"/api/v1/reviews/{created['id']}/report")
    assert resp.status_code == 200
    assert "# 代码审查报告" in resp.text
    assert "SQL 注入风险" in resp.text
    assert "函数命名不规范" in resp.text
    assert resp.headers["content-type"].startswith("text/markdown")


@pytest.mark.asyncio
async def test_download_html_report(client):
    project_id = await _create_project(client)
    with _patch_all():
        created = (await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "full"},
        )).json()

    resp = await client.get(f"/api/v1/reviews/{created['id']}/report/html")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text
    assert "代码审查报告" in resp.text
    assert "SQL 注入风险" in resp.text
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_findings_listing(client):
    project_id = await _create_project(client)
    with _patch_all():
        created = (await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project_id, "review_type": "full"},
        )).json()

    resp = await client.get(f"/api/v1/findings", params={"review_id": created["id"]})
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings) == 4
    agent_names = {f["agent_name"] for f in findings}
    assert agent_names == {"security", "code_style"}

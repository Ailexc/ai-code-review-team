"""增量审查（Git diff）集成测试"""

import pytest
from unittest.mock import patch


def _sample_project():
    return {"name": "增量审查项目", "language": "python", "path": "/tmp/incremental-project"}


@pytest.mark.asyncio
async def test_run_incremental_no_changes_returns_400(client):
    """非 Git 仓库或无变更应返回 400"""
    project_id = (await client.post("/api/v1/projects", json=_sample_project())).json()["id"]
    resp = await client.post(
        "/api/v1/reviews/run-incremental",
        params={"project_id": project_id},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_incremental_with_changes(client):
    """有变更时应只审查变更文件"""
    project_id = (await client.post("/api/v1/projects", json=_sample_project())).json()["id"]

    # mock diff parser 返回变更文件
    fake_diff = type("D", (), {
        "changed_file_paths": ["app/main.py", "app/utils.py"],
        "total_added_lines": 10,
    })()

    class FakeAgent:
        async def analyze(self, project_path, file_paths=None):
            # 验证传入的 file_paths 是变更文件列表
            assert file_paths == ["app/main.py", "app/utils.py"]
            return [{"rule_id": "INC-1", "severity": "warning", "message": "变更引入问题", "file_path": "app/main.py", "line_start": 12}]

    with patch("app.services.diff_parser.get_changed_files", lambda *a, **k: fake_diff), \
         patch.dict("app.services.review_service.AGENT_REGISTRY", {"security": (FakeAgent, "security", "security")}):
        resp = await client.post(
            "/api/v1/reviews/run-incremental",
            params={"project_id": project_id, "review_type": "security"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["trigger_type"] == "incremental"
    assert data["total_findings"] == 1


@pytest.mark.asyncio
async def test_run_incremental_project_not_found(client):
    resp = await client.post(
        "/api/v1/reviews/run-incremental",
        params={"project_id": "nonexistent"},
    )
    assert resp.status_code == 404

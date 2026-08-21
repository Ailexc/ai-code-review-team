"""项目 CRUD API 集成测试"""

import pytest


def _sample_project():
    return {
        "name": "测试项目",
        "description": "集成测试用项目",
        "language": "python",
        "framework": "fastapi",
        "path": "/tmp/test-project",
    }


@pytest.mark.asyncio
async def test_create_project(client):
    resp = await client.post("/api/v1/projects", json=_sample_project())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试项目"
    assert data["id"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_duplicate_path_rejected(client):
    await client.post("/api/v1/projects", json=_sample_project())
    resp = await client.post("/api/v1/projects", json=_sample_project())
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_projects(client):
    await client.post("/api/v1/projects", json=_sample_project())
    await client.post("/api/v1/projects", json={**_sample_project(), "name": "第二个", "path": "/tmp/test-project-2"})
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_search_projects(client):
    await client.post("/api/v1/projects", json=_sample_project())
    resp = await client.get("/api/v1/projects", params={"search": "测试"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_filter_by_language(client):
    await client.post("/api/v1/projects", json=_sample_project())
    resp = await client.get("/api/v1/projects", params={"language": "go"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_project(client):
    created = (await client.post("/api/v1/projects", json=_sample_project())).json()
    resp = await client.get(f"/api/v1/projects/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "测试项目"


@pytest.mark.asyncio
async def test_get_project_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(client):
    created = (await client.post("/api/v1/projects", json=_sample_project())).json()
    resp = await client.put(
        f"/api/v1/projects/{created['id']}",
        json={"name": "改名后", "is_active": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "改名后"
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_project(client):
    created = (await client.post("/api/v1/projects", json=_sample_project())).json()
    resp = await client.delete(f"/api/v1/projects/{created['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/projects/{created['id']}")
    assert resp.status_code == 404

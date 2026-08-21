"""LLM 模型配置 API 集成测试"""

import pytest


def _sample_config():
    return {
        "name": "测试模型",
        "provider": "custom",
        "model": "test-model",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test-123",
        "max_tokens": 4096,
        "temperature": 0.1,
        "is_default": False,
        "is_enabled": True,
    }


@pytest.mark.asyncio
async def test_create_config(client):
    resp = await client.post("/api/v1/llm-configs", json=_sample_config())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试模型"
    assert data["api_key_set"] is True
    # API Key 不应明文返回
    assert "api_key" not in data


@pytest.mark.asyncio
async def test_create_duplicate_name_rejected(client):
    await client.post("/api/v1/llm-configs", json=_sample_config())
    resp = await client.post("/api/v1/llm-configs", json=_sample_config())
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_configs(client):
    await client.post("/api/v1/llm-configs", json=_sample_config())
    resp = await client.get("/api/v1/llm-configs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_set_default_clears_others(client):
    first = (await client.post("/api/v1/llm-configs", json=_sample_config())).json()
    second_data = {**_sample_config(), "name": "第二个", "is_default": True}
    second = (await client.post("/api/v1/llm-configs", json=second_data)).json()

    assert second["is_default"] is True
    # 第一个应被取消默认
    resp = await client.get("/api/v1/llm-configs")
    configs = {c["id"]: c for c in resp.json()}
    assert configs[first["id"]]["is_default"] is False


@pytest.mark.asyncio
async def test_update_config(client):
    created = (await client.post("/api/v1/llm-configs", json=_sample_config())).json()
    resp = await client.put(f"/api/v1/llm-configs/{created['id']}", json={"name": "改名"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名"


@pytest.mark.asyncio
async def test_delete_config(client):
    created = (await client.post("/api/v1/llm-configs", json=_sample_config())).json()
    resp = await client.delete(f"/api/v1/llm-configs/{created['id']}")
    assert resp.status_code == 204
    resp = await client.get("/api/v1/llm-configs")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_test_connection_no_key(client):
    created = (await client.post(
        "/api/v1/llm-configs",
        json={**_sample_config(), "api_key": None},
    )).json()
    resp = await client.post(f"/api/v1/llm-configs/{created['id']}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "API Key" in data["message"]


@pytest.mark.asyncio
async def test_test_connection_missing_config(client):
    resp = await client.post("/api/v1/llm-configs/nonexistent/test")
    assert resp.status_code == 404

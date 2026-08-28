"""发现管理 API 集成测试"""

import pytest

from helpers import patch_review_flow

FAKE_FINDINGS = [
    {
        "severity": "critical",
        "message": "SQL 注入风险",
        "file_path": "app/main.py",
        "line_start": 10,
        "code_snippet": "SELECT * FROM users",
        "suggestion": "使用参数化查询",
    },
    {
        "severity": "warning",
        "message": "未使用的变量",
        "file_path": "app/utils.py",
        "line_start": 20,
        "code_snippet": "unused = 1",
        "suggestion": "删除未使用的变量",
        "is_auto_fixable": True,
    },
]


async def _create_review_with_findings(client):
    """创建项目并执行审查，返回 (project_id, review_id, findings)"""
    resp = await client.post("/api/v1/projects", json={
        "name": "Finding 测试项目",
        "language": "python",
        "path": "/tmp/finding-test",
    })
    project = (await client.get("/api/v1/projects")).json()["items"][0]

    with patch_review_flow({"security": FAKE_FINDINGS}):
        resp = await client.post(
            "/api/v1/reviews/run",
            params={"project_id": project["id"], "review_type": "security"},
        )
    assert resp.status_code == 201
    review = resp.json()

    resp = await client.get("/api/v1/findings", params={"review_id": review["id"]})
    assert resp.status_code == 200
    findings = resp.json()

    return project["id"], review["id"], findings


@pytest.mark.asyncio
async def test_list_findings(client):
    """获取发现列表（含 review_id 筛选）"""
    _, review_id, findings = await _create_review_with_findings(client)
    assert len(findings) == 2
    assert findings[0]["review_id"] == review_id


@pytest.mark.asyncio
async def test_get_finding_detail(client):
    """获取单个发现详情"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    resp = await client.get(f"/api/v1/findings/{finding_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == finding_id
    assert data["severity"] == "critical"


@pytest.mark.asyncio
async def test_get_finding_not_found(client):
    """获取不存在的发现返回 404"""
    resp = await client.get("/api/v1/findings/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_finding_status_open_to_acknowledged(client):
    """更新发现状态：open → acknowledged"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "acknowledged"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "acknowledged"
    assert data["id"] == finding_id


@pytest.mark.asyncio
async def test_update_finding_status_to_fixed(client):
    """更新发现状态：open → fixed"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "fixed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fixed"


@pytest.mark.asyncio
async def test_update_finding_status_full_cycle(client):
    """发现状态完整流转：open → acknowledged → fixed"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    # open → acknowledged
    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "acknowledged"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"

    # acknowledged → fixed
    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "fixed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "fixed"

    # 确认持久化
    resp = await client.get(f"/api/v1/findings/{finding_id}")
    assert resp.json()["status"] == "fixed"


@pytest.mark.asyncio
async def test_update_finding_status_back_to_open(client):
    """发现状态回退：acknowledged → open"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "acknowledged"},
    )

    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "open"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


@pytest.mark.asyncio
async def test_update_finding_status_not_found(client):
    """更新不存在的发现状态返回 404"""
    resp = await client.put(
        "/api/v1/findings/nonexistent-id/status",
        json={"status": "fixed"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_finding_status_invalid_value(client):
    """更新发现状态为非法值返回 422"""
    _, _, findings = await _create_review_with_findings(client)
    finding_id = findings[0]["id"]

    resp = await client.put(
        f"/api/v1/findings/{finding_id}/status",
        json={"status": "invalid_status"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_findings_filter_by_status(client):
    """按状态筛选发现列表"""
    _, _, findings = await _create_review_with_findings(client)

    # 将第一个 finding 标记为 fixed
    await client.put(
        f"/api/v1/findings/{findings[0]['id']}/status",
        json={"status": "fixed"},
    )

    # 筛选 fixed
    resp = await client.get("/api/v1/findings", params={"status": "fixed"})
    assert resp.status_code == 200
    fixed_findings = resp.json()
    assert len(fixed_findings) == 1
    assert fixed_findings[0]["status"] == "fixed"

    # 筛选 open（应少一个）
    resp = await client.get("/api/v1/findings", params={"status": "open"})
    assert resp.status_code == 200
    open_findings = resp.json()
    assert len(open_findings) == 1


@pytest.mark.asyncio
async def test_update_finding_status_persists_in_stats(client):
    """fixed 状态更新应反映在 /system/stats 中"""
    _, _, findings = await _create_review_with_findings(client)

    # 初始状态应无 fixed
    resp = await client.get("/api/v1/system/stats")
    assert resp.json()["findings_fixed"] == 0

    # 标记一个为 fixed
    await client.put(
        f"/api/v1/findings/{findings[0]['id']}/status",
        json={"status": "fixed"},
    )

    # stats 应更新
    resp = await client.get("/api/v1/system/stats")
    data = resp.json()
    assert data["findings_fixed"] == 1
    assert data["findings_status_distribution"]["fixed"] == 1

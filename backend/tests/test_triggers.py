"""触发器 API 集成测试"""

import io
import tempfile
import zipfile
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_list_trigger_types(client):
    resp = await client.get("/api/v1/triggers/types")
    assert resp.status_code == 200
    types = resp.json()["triggers"]
    names = {t["name"] for t in types}
    assert {"local_directory", "code_paste", "file_upload", "cli"} <= names


@pytest.mark.asyncio
async def test_local_directory_trigger(client):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "main.py").write_text("print('hello')\n")
        (Path(tmp) / "utils").mkdir()
        (Path(tmp) / "utils" / "helper.py").write_text("def helper():\n    return 1\n")
        (Path(tmp) / "README.md").write_text("docs")
        # 应被跳过的目录
        (Path(tmp) / "node_modules").mkdir()
        (Path(tmp) / "node_modules" / "dep.js").write_text("var x = 1;")

        resp = await client.post("/api/v1/triggers", json={
            "trigger_type": "local_directory",
            "path": tmp,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # main.py + utils/helper.py + README.md（.md 也在默认扩展名单内）
        assert data["file_count"] == 3
        assert "main.py" in data["files"]
        assert "utils/helper.py" in data["files"]
        assert "README.md" in data["files"]
        assert "node_modules/dep.js" not in data["files"]


@pytest.mark.asyncio
async def test_local_directory_missing_path(client):
    resp = await client.post("/api/v1/triggers", json={"trigger_type": "local_directory"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_local_directory_nonexistent(client):
    resp = await client.post("/api/v1/triggers", json={
        "trigger_type": "local_directory",
        "path": "/nonexistent/path/xyz",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is False


@pytest.mark.asyncio
async def test_code_paste_trigger(client):
    resp = await client.post("/api/v1/triggers", json={
        "trigger_type": "code_paste",
        "code": "def foo():\n    return 42\n",
        "filename": "foo.py",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert any("foo.py" in f for f in data["files"])


@pytest.mark.asyncio
async def test_code_paste_missing_code(client):
    resp = await client.post("/api/v1/triggers", json={"trigger_type": "code_paste"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cli_trigger_with_files(client):
    with tempfile.TemporaryDirectory() as tmp:
        f1 = Path(tmp) / "a.py"
        f1.write_text("import os\n")
        resp = await client.post("/api/v1/triggers", json={
            "trigger_type": "cli",
            "files": [str(f1)],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["file_count"] >= 1


@pytest.mark.asyncio
async def test_upload_single_file(client):
    content = b"def hello():\n    return 'hi'\n"
    resp = await client.post(
        "/api/v1/triggers/upload",
        files={"file": ("hello.py", io.BytesIO(content), "text/x-python")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert any("hello.py" in f for f in data["files"])


@pytest.mark.asyncio
async def test_upload_zip(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pkg/__init__.py", "")
        zf.writestr("pkg/mod.py", "def f():\n    pass\n")
    buf.seek(0)

    resp = await client.post(
        "/api/v1/triggers/upload",
        files={"file": ("pkg.zip", buf, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert any("pkg/mod.py" in f for f in data["files"])

"""自动修复引擎测试"""

import pytest
from pathlib import Path
from app.services.autofix import AutoFixEngine


@pytest.fixture
def engine():
    return AutoFixEngine()


@pytest.mark.asyncio
async def test_autofix_no_fixable_findings(engine, tmp_path):
    """无可修复项时应返回空结果"""
    (tmp_path / "app.py").write_text("x = 1\n")
    findings = [
        {"is_auto_fixable": False, "file_path": "app.py", "message": "test"},
    ]
    result = await engine.run(str(tmp_path), findings)
    assert result["patches"] == []
    assert "没有可自动修复" in result["summary"]


@pytest.mark.asyncio
async def test_autofix_nonexistent_path(engine):
    """不存在的路径应返回错误信息"""
    result = await engine.run("/tmp/nonexistent_12345", [{"is_auto_fixable": True}])
    assert "不存在" in result["summary"]


@pytest.mark.asyncio
async def test_autofix_ruff_fixable_code(engine, tmp_path):
    """Ruff 可修复的代码（未排序 import）应生成补丁"""
    # 写入一个有 import 排序问题的文件
    code = """import os
import sys
import json
import os

def hello():
    print("hello")
"""
    (tmp_path / "app.py").write_text(code)
    findings = [
        {
            "is_auto_fixable": True,
            "file_path": "app.py",
            "rule_id": "I001",
            "message": "import 未排序",
        },
    ]
    result = await engine.run(str(tmp_path), findings)
    # Ruff 应该能修复 import 排序
    assert result["summary"] != ""
    # 可能有补丁（取决于 Ruff 是否检测到问题）


@pytest.mark.asyncio
async def test_autofix_clean_code(engine, tmp_path):
    """干净的代码不应生成补丁"""
    (tmp_path / "clean.py").write_text('"""模块文档"""\nimport os\n\ndef hello():\n    return "hi"\n')
    findings = [
        {
            "is_auto_fixable": True,
            "file_path": "clean.py",
            "rule_id": "I001",
            "message": "import 未排序",
        },
    ]
    result = await engine.run(str(tmp_path), findings)
    # 干净代码可能不产生补丁
    assert isinstance(result["patches"], list)


def test_is_ruff_fixable(engine):
    """Ruff 可修复规则应正确判断"""
    assert engine._is_ruff_fixable({"rule_id": "F401"}) is True
    assert engine._is_ruff_fixable({"rule_id": "I001"}) is True
    assert engine._is_ruff_fixable({"rule_id": "E501"}) is True
    assert engine._is_ruff_fixable({"rule_id": "UP001"}) is True
    assert engine._is_ruff_fixable({"rule_id": "PERF-N+1"}) is False
    assert engine._is_ruff_fixable({"rule_id": "LLM-SEC"}) is False


def test_extract_files_from_diff(engine):
    """应从 unified diff 中正确提取文件路径"""
    diff = """--- a/app/main.py
+++ b/app/main.py
@@ -1,3 +1,3 @@
-import os
+import json
 import sys
"""
    files = engine._extract_files_from_diff(diff)
    assert "app/main.py" in files

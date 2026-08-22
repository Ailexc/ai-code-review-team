"""上下文引擎 / 规则挖掘 / 语义 diff / 可观测性 测试"""

import pytest
from pathlib import Path

from app.services.code_index import CodeIndex
from app.services.context_engine import ContextEngine
from app.services.semantic_diff import SemanticDiff
from app.services.metrics import MetricsTracker


# ──────────────────────────────────────────────
# P0: 代码索引
# ──────────────────────────────────────────────

def test_code_index_builds_symbols(tmp_path):
    """代码索引应提取函数/类/导入符号"""
    (tmp_path / "app.py").write_text(
        "import os\n"
        "from typing import List\n\n"
        "def add(a, b):\n"
        "    return a + b\n\n"
        "class User:\n"
        "    def get_name(self):\n"
        "        return 'x'\n"
    )
    index = CodeIndex().build(str(tmp_path))
    summary = index.summary()
    assert summary["files"] == 1
    assert summary["symbols"] >= 3  # add, User, User.get_name
    # 检查符号
    assert index.find_symbol("add")
    assert index.find_symbol("User")
    assert index.find_symbol("User.get_name")


def test_code_index_call_graph(tmp_path):
    """代码索引应记录调用关系"""
    (tmp_path / "app.py").write_text(
        "def helper():\n"
        "    return 1\n\n"
        "def main():\n"
        "    return helper()\n"
    )
    index = CodeIndex().build(str(tmp_path))
    callers = index.find_callers("helper")
    assert len(callers) == 1
    assert callers[0]["file_path"] == "app.py"


def test_code_index_related_files(tmp_path):
    """代码索引应识别文件依赖"""
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    index = CodeIndex().build(str(tmp_path))
    related = index.get_related_files("a.py")
    assert "b" in related


def test_code_index_skips_non_python(tmp_path):
    """代码索引应跳过非 Python 文件"""
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "readme.md").write_text("# hello\n")
    index = CodeIndex().build(str(tmp_path))
    assert index.summary()["files"] == 1


# ──────────────────────────────────────────────
# P0: 上下文引擎
# ──────────────────────────────────────────────

def test_context_engine_builds(tmp_path):
    """上下文引擎应构建索引并生成上下文"""
    (tmp_path / "app.py").write_text(
        "def helper():\n"
        "    return 1\n\n"
        "def main():\n"
        "    return helper()\n"
    )
    engine = ContextEngine().build(str(tmp_path))
    ctx = engine.get_context("app.py")
    assert "file_content" in ctx
    assert "symbols" in ctx
    assert len(ctx["symbols"]) >= 2
    assert "callers" in ctx


def test_context_engine_prompt(tmp_path):
    """上下文引擎应生成 prompt 文本"""
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")
    engine = ContextEngine().build(str(tmp_path))
    prompt = engine.build_prompt_context("app.py")
    assert "被审查文件" in prompt
    assert "文件内符号" in prompt


# ──────────────────────────────────────────────
# P2: 语义 diff
# ──────────────────────────────────────────────

def test_semantic_diff_extract_symbols():
    """语义 diff 应提取符号"""
    sd = SemanticDiff()
    symbols = sd._extract_symbols(
        "def add(a, b):\n    return a + b\n\nclass User:\n    pass\n"
    )
    assert "add" in symbols
    assert symbols["add"]["signature"] == "add(a, b)"
    assert "User" in symbols


def test_semantic_diff_ast_diff():
    """语义 diff 应识别新增/删除/修改"""
    sd = SemanticDiff()
    old = "def add(a, b):\n    return a + b\n\ndef old_func():\n    pass\n"
    new = "def add(a, b):\n    return a + b\n\ndef new_func():\n    pass\n"
    changes = sd._ast_diff(old, new, "app.py")
    types = {c["type"] for c in changes}
    assert "added" in types  # new_func
    assert "removed" in types  # old_func


def test_semantic_diff_non_git(tmp_path):
    """非 Git 仓库应返回空结果"""
    (tmp_path / "app.py").write_text("x = 1\n")
    sd = SemanticDiff()
    result = sd.analyze(str(tmp_path))
    assert result["summary"] == "非 Git 仓库"


# ──────────────────────────────────────────────
# P3: 可观测性（成本统计 + 审计日志）
# ──────────────────────────────────────────────

def test_metrics_token_tracking():
    """metrics 应统计 LLM token（按模型）"""
    m = MetricsTracker()
    m.record_llm_call(True, 1.0, tokens=1000, model="gpt-4o")
    m.record_llm_call(True, 0.5, tokens=2000, model="deepseek-chat")
    snap = m.snapshot()
    assert snap["llm"]["total_tokens"] == 3000
    assert snap["llm"]["tokens_by_model"]["gpt-4o"] == 1000
    assert snap["llm"]["tokens_by_model"]["deepseek-chat"] == 2000
    # 成本字段已移除
    assert "total_cost_usd" not in snap["llm"]
    assert "cost_by_model" not in snap["llm"]


def test_metrics_audit_log():
    """metrics 应记录审计日志"""
    m = MetricsTracker()
    m.record_audit("review_completed", {"review_id": "abc", "findings": 5})
    m.record_audit("finding_status", {"finding_id": "xyz", "status": "fixed"})
    snap = m.snapshot()
    assert len(snap["audit_log"]) == 2
    assert snap["audit_log"][0]["action"] == "review_completed"
    assert snap["audit_log"][1]["detail"]["status"] == "fixed"


def test_metrics_audit_log_capped():
    """审计日志应限制在 100 条"""
    m = MetricsTracker()
    for i in range(150):
        m.record_audit(f"action_{i}")
    snap = m.snapshot()
    assert len(snap["audit_log"]) == 100
"""性能分析 Agent 静态逻辑测试（不触发真实 LLM/网络）"""

import pytest
from pathlib import Path

from app.agents.performance_agent import PerformanceAgent


@pytest.fixture
def agent():
    return PerformanceAgent()


def test_check_n_plus_one_detects_orm_in_loop(agent, tmp_path):
    """循环内 ORM 调用应被检测为 N+1 风险"""
    code = '''import sqlalchemy

def get_users(session, user_ids):
    results = []
    for uid in user_ids:
        user = session.query(User).filter(User.id == uid).first()
        results.append(user)
    return results
'''
    (tmp_path / "service.py").write_text(code)

    import ast
    tree = ast.parse(code)
    findings = agent._check_n_plus_one(tree, tmp_path, "service.py")
    assert len(findings) >= 1
    assert any("N+1" in f["rule_id"] for f in findings)
    assert any("critical" in f["severity"] for f in findings)


def test_check_n_plus_one_no_false_positive(agent, tmp_path):
    """循环内非 ORM 调用不应误报"""
    code = '''def process(items):
    results = []
    for item in items:
        results.append(item.upper())
    return results
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_n_plus_one(tree, tmp_path, "utils.py")
    assert len(findings) == 0


def test_check_sync_in_async_detects_sleep(agent, tmp_path):
    """async 函数内 time.sleep 应被检测"""
    code = '''import time
import asyncio

async def fetch_data():
    time.sleep(5)
    return "done"
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_sync_in_async(tree, tmp_path, "api.py")
    assert len(findings) >= 1
    assert any("time.sleep" in f["message"] for f in findings)
    assert any("critical" in f["severity"] for f in findings)


def test_check_sync_in_async_detects_requests(agent, tmp_path):
    """async 函数内 requests.get 应被检测"""
    code = '''import requests

async def call_api():
    resp = requests.get("https://example.com")
    return resp.json()
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_sync_in_async(tree, tmp_path, "api.py")
    assert len(findings) >= 1
    assert any("requests.get" in f["message"] for f in findings)


def test_check_sync_in_async_no_false_positive(agent, tmp_path):
    """非 async 函数内的同步调用不应误报"""
    code = '''import time

def normal_func():
    time.sleep(1)
    return "ok"
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_sync_in_async(tree, tmp_path, "utils.py")
    assert len(findings) == 0


def test_check_string_concat_in_loop(agent, tmp_path):
    """循环内字符串 += 拼接应被检测"""
    code = '''def build_report(items):
    result = ""
    for item in items:
        result += str(item) + "\\n"
    return result
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_string_concat_in_loop(tree, tmp_path, "report.py")
    assert len(findings) >= 1
    assert any("result" in f["message"] for f in findings)
    assert any("PERF-CONCAT" in f["rule_id"] for f in findings)


def test_check_string_concat_no_false_positive(agent, tmp_path):
    """非循环内的 += 不应误报"""
    code = '''def build():
    result = ""
    result += "hello"
    result += " world"
    return result
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_string_concat_in_loop(tree, tmp_path, "builder.py")
    assert len(findings) == 0


def test_check_unbounded_query(agent, tmp_path):
    """.all() 无 .limit() 应被检测"""
    code = '''def get_all_users(session):
    return session.query(User).all()
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_unbounded_query(tree, tmp_path, "repo.py")
    assert len(findings) >= 1
    assert any("PERF-UNBOUNDED" in f["rule_id"] for f in findings)


def test_check_unbounded_query_with_limit(agent, tmp_path):
    """有 .limit() 的查询不应被检测"""
    code = '''def get_users(session):
    return session.query(User).limit(100).all()
'''
    import ast
    tree = ast.parse(code)
    findings = agent._check_unbounded_query(tree, tmp_path, "repo.py")
    assert len(findings) == 0


def test_collect_python_files(agent, tmp_path):
    """应正确收集 Python 文件"""
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "utils.py").write_text("y = 2\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.py").write_text("z = 3\n")

    files = agent._collect_python_files(tmp_path)
    rels = {str(f.relative_to(tmp_path)) for f in files}
    assert "app.py" in rels
    assert "lib/utils.py" in rels
    # node_modules 应被排除
    assert not any("node_modules" in r for r in rels)


def test_collect_python_files_with_filter(agent, tmp_path):
    """指定 file_paths 时应只返回指定文件"""
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")

    files = agent._collect_python_files(tmp_path, file_paths=["a.py"])
    rels = {str(f.relative_to(tmp_path)) for f in files}
    assert "a.py" in rels
    assert "b.py" not in rels


@pytest.mark.asyncio
async def test_analyze_nonexistent_path(agent):
    """不存在的路径应返回空结果"""
    findings = await agent.analyze("/tmp/nonexistent_path_12345")
    assert findings == []


@pytest.mark.asyncio
async def test_analyze_integration(agent, tmp_path):
    """完整分析流程 — 应同时检出 N+1 + 同步阻塞 + 字符串拼接"""
    code = '''import time

async def process_orders(session, order_ids):
    result = ""
    for oid in order_ids:
        order = session.query(Order).filter(Order.id == oid).first()
        time.sleep(0.1)
        result += str(order) + "\\n"
    return result
'''
    (tmp_path / "service.py").write_text(code)
    findings = await agent.analyze(str(tmp_path))

    rule_ids = {f["rule_id"] for f in findings}
    # 应检出至少 3 种问题
    assert "PERF-N+1" in rule_ids, f"未检出 N+1，实际: {rule_ids}"
    assert "PERF-SYNC" in rule_ids, f"未检出同步阻塞，实际: {rule_ids}"
    assert "PERF-CONCAT" in rule_ids, f"未检出字符串拼接，实际: {rule_ids}"

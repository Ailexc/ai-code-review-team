"""依赖审查与测试覆盖 Agent 的静态逻辑测试（不触发真实 LLM/网络）"""

import pytest
from pathlib import Path

from app.agents.dependency_agent import DependencyAgent
from app.agents.test_coverage_agent import TestCoverageAgent


def test_dependency_agent_parses_pip_audit(tmp_path):
    """验证 pip-audit JSON 解析逻辑"""
    agent = DependencyAgent()
    path = tmp_path
    data = {
        "dependencies": [
            {
                "name": "requests",
                "version": "2.20.0",
                "vulns": [
                    {
                        "id": "CVE-2018-XXXX",
                        "description": "A flaw was found in requests",
                        "fix_versions": ["2.20.1"],
                        "cve": {"cvss_score": 7.5},
                    }
                ],
            }
        ]
    }
    findings = agent._parse_pip_audit(path, data)
    assert len(findings) == 1
    f = findings[0]
    assert f["severity"] == "warning"  # 7.5 >= 7.0
    assert "requests" in f["message"]
    assert "2.20.1" in f["suggestion"]


def test_dependency_score_to_severity():
    agent = DependencyAgent()
    assert agent._score_to_severity(9.5) == "critical"
    assert agent._score_to_severity(7.0) == "warning"
    assert agent._score_to_severity(5.0) == "suggestion"
    assert agent._score_to_severity(None) == "warning"


def test_dependency_collect_manifest(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\nsqlalchemy\n")
    (tmp_path / "package.json").write_text('{"dependencies": {"axios": "^1.0"}}')
    agent = DependencyAgent()
    manifest = agent._collect_manifest(tmp_path)
    names = [m[0] for m in manifest]
    assert "requirements.txt" in names
    assert "package.json" in names


def test_test_coverage_finds_untested_functions(tmp_path):
    """AST 分析应识别未被测试引用的函数"""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "def _private():\n    return 1\n\n"
        "def tested_func():\n    return 2\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from app.calc import tested_func\n\ndef test_it():\n    assert tested_func() == 2\n"
    )

    agent = TestCoverageAgent()
    findings = agent._analyze_coverage(tmp_path)
    messages = [f["message"] for f in findings]
    # add 未被测试引用 → 应被标记
    assert any("`add`" in m for m in messages)
    # tested_func 被测试引用 → 不应被标记
    assert not any("`tested_func`" in m for m in messages)
    # 私有函数 _private 应跳过
    assert not any("`_private`" in m for m in messages)


def test_test_coverage_warns_no_tests(tmp_path):
    """无测试文件的项目应给出警告"""
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")
    agent = TestCoverageAgent()
    findings = agent._analyze_coverage(tmp_path)
    assert any("未发现测试目录" in f["message"] for f in findings)


def test_test_coverage_skips_test_functions(tmp_path):
    """测试文件自身的函数不应被标记为未测试"""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_thing():\n    assert True\n"
    )
    agent = TestCoverageAgent()
    findings = agent._analyze_coverage(tmp_path)
    assert not any("test_thing" in f["message"] for f in findings)

"""Git 审查 Agent 静态逻辑测试"""

import pytest
import subprocess
from pathlib import Path
from app.agents.git_review_agent import GitReviewAgent, CONVENTIONAL_RE, BRANCH_PATTERN


@pytest.fixture
def agent():
    return GitReviewAgent()


def _init_git_repo(path: Path, commits=None):
    """初始化一个 Git 仓库并创建提交"""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True)

    if commits:
        for msg, files in commits:
            for fname, content in files.items():
                (path / fname).write_text(content)
            subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True)
            subprocess.run(["git", "commit", "-m", msg], cwd=str(path), capture_output=True)


def test_conventional_commit_regex():
    """Conventional Commits 正则应正确匹配"""
    assert CONVENTIONAL_RE.match("feat: add login")
    assert CONVENTIONAL_RE.match("fix(auth): resolve token issue")
    assert CONVENTIONAL_RE.match("docs: update README")
    assert CONVENTIONAL_RE.match("feat!: breaking change")
    assert not CONVENTIONAL_RE.match("Add login")  # 无 type 前缀
    assert not CONVENTIONAL_RE.match("fix")  # 无描述
    assert not CONVENTIONAL_RE.match("")  # 空


def test_branch_pattern():
    """分支命名正则应正确匹配"""
    assert BRANCH_PATTERN.match("feature/user-auth")
    assert BRANCH_PATTERN.match("fix/login-bug")
    assert BRANCH_PATTERN.match("release/v1.0")
    assert BRANCH_PATTERN.match("main")
    assert not BRANCH_PATTERN.match("random-branch-name")
    assert not BRANCH_PATTERN.match("abc")


def test_check_commit_conventions_good(agent, tmp_path):
    """规范的提交不应产生 warning"""
    _init_git_repo(tmp_path, [
        ("feat: add user auth", {"auth.py": "def login(): pass"}),
        ("fix: resolve timeout", {"net.py": "timeout = 30"}),
        ("docs: update README", {"README.md": "# Hello"}),
    ])
    findings = agent._check_commit_conventions(tmp_path)
    warnings = [f for f in findings if f["severity"] == "warning"]
    assert len(warnings) == 0


def test_check_commit_conventions_bad(agent, tmp_path):
    """不规范的提交应产生 warning"""
    _init_git_repo(tmp_path, [
        ("add stuff", {"a.py": "x = 1"}),
        ("fix", {"b.py": "y = 2"}),
        ("update", {"c.py": "z = 3"}),
        ("wip", {"d.py": "w = 4"}),
        ("random commit message", {"e.py": "v = 5"}),
    ])
    findings = agent._check_commit_conventions(tmp_path)
    warnings = [f for f in findings if f["severity"] == "warning"]
    assert len(warnings) >= 1
    assert any("Conventional Commits" in f["message"] for f in warnings)


def test_check_branch_strategy_standard(agent, tmp_path):
    """标准分支不应产生告警"""
    _init_git_repo(tmp_path, [
        ("feat: init", {"a.py": "x = 1"}),
    ])
    findings = agent._check_branch_strategy(tmp_path)
    branch_findings = [f for f in findings if f["rule_id"] == "GIT-BRANCH"]
    # main 分支是标准的
    assert len(branch_findings) == 0


def test_check_branch_strategy_non_standard(agent, tmp_path):
    """非标准分支命名应产生告警"""
    _init_git_repo(tmp_path, [
        ("feat: init", {"a.py": "x = 1"}),
    ])
    # 创建非标准分支
    subprocess.run(["git", "checkout", "-b", "my-random-branch"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=str(tmp_path), capture_output=True)

    findings = agent._check_branch_strategy(tmp_path)
    branch_findings = [f for f in findings if f["rule_id"] == "GIT-BRANCH"]
    assert len(branch_findings) >= 1


def test_analyze_contributions(agent, tmp_path):
    """贡献统计应能正常运行"""
    _init_git_repo(tmp_path, [
        ("feat: a", {"a.py": "x = 1"}),
        ("feat: b", {"b.py": "y = 2"}),
        ("feat: c", {"c.py": "z = 3"}),
    ])
    findings = agent._analyze_contributions(tmp_path)
    # 应能正常返回（可能为空，取决于提交数量）
    assert isinstance(findings, list)


def test_run_git_timeout(agent, tmp_path):
    """git 命令超时应返回空字符串"""
    # 非 git 仓库
    result = agent._run_git(tmp_path, ["log"])
    assert result == ""


@pytest.mark.asyncio
async def test_analyze_non_git_repo(agent, tmp_path):
    """非 Git 仓库应返回空结果"""
    (tmp_path / "app.py").write_text("x = 1\n")
    findings = await agent.analyze(str(tmp_path))
    assert findings == []


@pytest.mark.asyncio
async def test_analyze_with_git_repo(agent, tmp_path):
    """Git 仓库应能正常分析"""
    _init_git_repo(tmp_path, [
        ("add stuff", {"a.py": "x = 1"}),
        ("fix", {"b.py": "y = 2"}),
        ("random commit", {"c.py": "z = 3"}),
        ("another random", {"d.py": "w = 4"}),
        ("yet another", {"e.py": "v = 5"}),
        ("more random", {"f.py": "u = 6"}),
    ])
    findings = await agent.analyze(str(tmp_path))
    # 应检出不规范提交
    assert isinstance(findings, list)
    # 至少应有提交规范相关发现
    rule_ids = {f["rule_id"] for f in findings}
    assert any("GIT" in r for r in rule_ids), f"未检出 Git 相关问题，实际: {rule_ids}"

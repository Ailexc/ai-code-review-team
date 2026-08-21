"""Git diff 解析器 — 提取变更文件与变更行范围，用于增量审查

只审查变更部分，控制 token 成本，贴合真实 PR/diff 审查场景。
"""

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

# diff 行模式
DIFF_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class ChangedFile:
    """单个变更文件"""
    path: str
    status: str = "modified"  # added / modified / deleted / renamed
    added_lines: list[int] = field(default_factory=list)  # 新增的行号（1-based）


@dataclass
class DiffResult:
    """diff 解析结果"""
    files: list[ChangedFile] = field(default_factory=list)
    base_ref: str = ""
    head_ref: str = ""

    @property
    def changed_file_paths(self) -> list[str]:
        return [f.path for f in self.files if f.status != "deleted"]

    @property
    def total_added_lines(self) -> int:
        return sum(len(f.added_lines) for f in self.files)


def parse_unified_diff(diff_text: str) -> DiffResult:
    """解析 unified diff 文本，提取变更文件与新增行号

    支持 git diff / git show 的输出格式。
    """
    result = DiffResult()
    current_file: ChangedFile | None = None
    current_new_line = 0

    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # diff --git a/xxx b/yyy
        if line.startswith("diff --git "):
            parts = line.split(" ")
            # 提取 b/ 路径
            if len(parts) >= 4:
                b_path = parts[-1]
                if b_path.startswith("b/"):
                    b_path = b_path[2:]
                current_file = ChangedFile(path=b_path, status="modified")
                result.files.append(current_file)
            i += 1
            continue

        # new file / deleted file / rename
        if line.startswith("new file mode"):
            if current_file:
                current_file.status = "added"
        elif line.startswith("deleted file mode"):
            if current_file:
                current_file.status = "deleted"
        elif line.startswith("rename from"):
            if current_file:
                current_file.status = "renamed"

        # +++ b/xxx 或 +++ /dev/null
        elif line.startswith("+++ ") and current_file:
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            if path != "/dev/null":
                current_file.path = path

        # @@ hunk header
        elif line.startswith("@@"):
            m = DIFF_HUNK_HEADER.match(line)
            if m and current_file:
                new_start = int(m.group(3))
                current_new_line = new_start

        # 新增行（+ 开头，非 +++）
        elif line.startswith("+") and not line.startswith("+++") and current_file and current_file.status != "deleted":
            current_file.added_lines.append(current_new_line)
            current_new_line += 1

        # 上下文行
        elif line.startswith(" ") and not line.startswith("---"):
            current_new_line += 1

        i += 1

    logger.info("diff 解析完成", files=len(result.files), added_lines=result.total_added_lines)
    return result


def get_git_diff(repo_path: str, base: str = "HEAD~1", head: str = "HEAD") -> str:
    """获取 git diff 文本

    Args:
        repo_path: Git 仓库路径
        base: 基准 ref（如 HEAD~1, main, 分支名）
        head: 目标 ref（默认 HEAD）
    """
    import subprocess
    from pathlib import Path

    repo = Path(repo_path)
    if not (repo / ".git").exists() and not repo.is_dir():
        logger.warning("非 Git 仓库或路径不存在", path=repo_path)
        return ""

    cmd = ["git", "diff", base, head, "--no-color"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=str(repo)
        )
        if result.returncode != 0:
            logger.warning("git diff 失败", stderr=result.stderr[:200])
            return ""
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("git diff 执行异常", error=str(e))
        return ""


def get_changed_files(repo_path: str, base: str = "HEAD~1", head: str = "HEAD") -> DiffResult:
    """获取变更文件列表与新增行（增量审查入口）"""
    diff_text = get_git_diff(repo_path, base, head)
    if not diff_text:
        return DiffResult()
    return parse_unified_diff(diff_text)

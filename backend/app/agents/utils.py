"""Agent 共享工具 — 代码片段提取与文件收集"""

from pathlib import Path

# LLM 分析支持的代码文件后缀
CODE_SUFFIXES = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go'}


def extract_code_snippet(
    project_path: Path,
    file_path: str,
    line_start: int | None,
    context: int = 3,
) -> str:
    """从源文件读取问题行附近的代码片段

    Args:
        project_path: 项目根目录
        file_path: 文件路径（相对或绝对）
        line_start: 起始行号（1 基）
        context: 行号前后各取多少行
    """
    if not line_start:
        return ""
    try:
        full = Path(file_path) if Path(file_path).is_absolute() else project_path / file_path
        if not full.exists():
            return ""
        lines = full.read_text(errors="ignore").splitlines()
        if not lines:
            return ""
        start = max(1, line_start - context)
        end = min(len(lines), line_start + context)
        return "\n".join(lines[start - 1:end])
    except Exception:
        return ""


def collect_code_files_for_llm(
    path: Path,
    file_paths: list[str] | None = None,
    max_files: int = 5,
    max_chars: int = 5000,
) -> list[tuple[str, str]]:
    """收集用于 LLM 分析的代码文件（限制数量与截断长度）

    Returns:
        [(相对路径, 内容), ...]
    """
    files = []
    if file_paths:
        for fp in file_paths[:max_files]:
            full_path = path / fp
            if full_path.exists() and full_path.suffix in CODE_SUFFIXES:
                files.append((fp, full_path.read_text(errors="ignore")[:max_chars]))
    else:
        for ext in ("*.py", "*.js", "*.ts", "*.tsx", "*.jsx"):
            for f in list(path.rglob(ext))[:10]:
                if "/node_modules/" not in str(f) and "/__pycache__/" not in str(f):
                    rel = str(f.relative_to(path))
                    files.append((rel, f.read_text(errors="ignore")[:max_chars]))
                    if len(files) >= max_files:
                        break
            if len(files) >= max_files:
                break
    return files

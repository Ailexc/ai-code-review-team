"""语义 Diff 服务 — AST 级结构化变更识别 + 调用图影响分析

对标 CodeRabbit 的 Change Stack / Qodo 的语义 diff：
1. AST 级 diff：识别函数/类级别的变更（而非行级）
2. 变更类型分类：新增 / 修改 / 删除 / 重构
3. 调用图影响：变更影响哪些调用方
"""

import ast
from pathlib import Path
from typing import Any

import structlog

from app.services.code_index import CodeIndex

logger = structlog.get_logger()


class SemanticDiff:
    """语义 Diff 分析器"""

    def __init__(self):
        self._index: CodeIndex | None = None

    def analyze(self, project_path: str, base: str = "HEAD~1", head: str = "HEAD") -> dict:
        """分析 Git 变更的语义影响

        Args:
            project_path: 项目路径
            base: 基准 commit
            head: 目标 commit

        Returns:
            { changed_files, structural_changes, impact_analysis, summary }
        """
        path = Path(project_path)
        if not path.exists() or not (path / ".git").exists():
            return {"changed_files": [], "structural_changes": [], "impact_analysis": [], "summary": "非 Git 仓库"}

        # 获取变更文件
        changed_files = self._get_changed_files(path, base, head)
        if not changed_files:
            return {"changed_files": [], "structural_changes": [], "impact_analysis": [], "summary": "无变更文件"}

        # 构建当前代码索引（用于调用图影响分析）
        self._index = CodeIndex().build(project_path)

        structural_changes = []
        for file_path in changed_files:
            try:
                old_content = self._get_file_at_commit(path, file_path, base)
                new_content = self._get_file_at_commit(path, file_path, head)
                changes = self._ast_diff(old_content, new_content, file_path)
                structural_changes.extend(changes)
            except Exception as e:
                logger.debug("语义 diff 跳过文件", file=file_path, error=str(e))

        # 调用图影响分析
        impact_analysis = self._analyze_impact(structural_changes)

        summary = {
            "changed_files": len(changed_files),
            "structural_changes": len(structural_changes),
            "impacted_callers": len(impact_analysis),
        }

        return {
            "changed_files": changed_files,
            "structural_changes": structural_changes,
            "impact_analysis": impact_analysis,
            "summary": summary,
        }

    def _get_changed_files(self, path: Path, base: str, head: str) -> list[str]:
        """获取变更文件列表"""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base, head],
                capture_output=True, text=True, timeout=30, cwd=str(path),
            )
            files = [f for f in result.stdout.splitlines() if f.endswith(".py")]
            return files
        except Exception:
            return []

    def _get_file_at_commit(self, path: Path, file_path: str, commit: str) -> str:
        """获取指定 commit 的文件内容"""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "show", f"{commit}:{file_path}"],
                capture_output=True, text=True, timeout=30, cwd=str(path),
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        # 回退：读取当前文件
        full = path / file_path
        if full.exists():
            return full.read_text(errors="ignore")
        return ""

    def _ast_diff(self, old_content: str, new_content: str, file_path: str) -> list[dict]:
        """AST 级 diff：识别函数/类级别的变更"""
        changes = []

        old_symbols = self._extract_symbols(old_content)
        new_symbols = self._extract_symbols(new_content)

        # 新增的符号
        for name, info in new_symbols.items():
            if name not in old_symbols:
                changes.append({
                    "type": "added",
                    "kind": info["kind"],
                    "name": name,
                    "file_path": file_path,
                    "line": info["line"],
                    "signature": info["signature"],
                    "description": f"新增 {info['kind']} `{name}`",
                })

        # 删除的符号
        for name, info in old_symbols.items():
            if name not in new_symbols:
                changes.append({
                    "type": "removed",
                    "kind": info["kind"],
                    "name": name,
                    "file_path": file_path,
                    "line": info["line"],
                    "signature": info["signature"],
                    "description": f"删除 {info['kind']} `{name}`",
                })

        # 修改的符号（签名变化）
        for name, info in new_symbols.items():
            if name in old_symbols and old_symbols[name]["signature"] != info["signature"]:
                changes.append({
                    "type": "modified",
                    "kind": info["kind"],
                    "name": name,
                    "file_path": file_path,
                    "line": info["line"],
                    "signature": info["signature"],
                    "old_signature": old_symbols[name]["signature"],
                    "description": f"修改 {info['kind']} `{name}` 签名: {old_symbols[name]['signature']} → {info['signature']}",
                })

        return changes

    def _extract_symbols(self, content: str) -> dict:
        """提取代码中的符号（函数/类）"""
        symbols = {}
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args]
                    symbols[node.name] = {
                        "kind": "function",
                        "line": node.lineno,
                        "signature": f"{node.name}({', '.join(args)})",
                    }
                elif isinstance(node, ast.ClassDef):
                    symbols[node.name] = {
                        "kind": "class",
                        "line": node.lineno,
                        "signature": node.name,
                    }
        except SyntaxError:
            pass
        return symbols

    def _analyze_impact(self, structural_changes: list[dict]) -> list[dict]:
        """分析变更的影响范围（调用图）"""
        impact = []
        if not self._index:
            return impact

        for change in structural_changes:
            if change["type"] in ("removed", "modified"):
                # 查找调用者
                callers = self._index.find_callers(change["name"])
                if callers:
                    impact.append({
                        "change": change,
                        "impacted_callers": callers,
                        "risk": "high" if change["type"] == "removed" else "medium",
                        "message": f"`{change['name']}` 被 {len(callers)} 处调用，变更可能影响这些调用方",
                    })
            elif change["type"] == "added":
                impact.append({
                    "change": change,
                    "impacted_callers": [],
                    "risk": "low",
                    "message": f"新增 `{change['name']}`，无现有调用方受影响",
                })

        return impact


# 全局单例
semantic_diff = SemanticDiff()
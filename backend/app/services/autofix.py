"""自动修复引擎 — 消费 is_auto_fixable 标记，生成修复补丁

支持两种修复路径：
1. Ruff 自动修复 — import 排序、格式化、简单 lint（确定性，直接改文件）
2. LLM 辅助修复 — 复杂代码问题的智能补丁（需人工确认）
"""

import difflib
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class AutoFixEngine:
    """自动修复引擎"""

    async def run(
        self,
        project_path: str,
        findings: list[dict[str, Any]],
        apply: bool = False,
    ) -> dict[str, Any]:
        """执行自动修复

        Args:
            project_path: 项目根目录
            findings: 审查发现列表（需含 is_auto_fixable、file_path、rule_id 等字段）
            apply: 是否直接应用修复（False = 仅生成补丁预览）

        Returns:
            { patches, fixed_files, skipped, summary }
        """
        path = Path(project_path)
        if not path.exists():
            return {"patches": [], "fixed_files": [], "skipped": [], "summary": "项目路径不存在"}

        fixable = [f for f in findings if f.get("is_auto_fixable")]
        if not fixable:
            return {"patches": [], "fixed_files": [], "skipped": [], "summary": "没有可自动修复的发现"}

        patches = []
        fixed_files = set()
        skipped = []

        # 1. Ruff 修复（import 排序、格式化等）
        ruff_patches, ruff_fixed = self._run_ruff_fix(path, apply)
        patches.extend(ruff_patches)
        fixed_files.update(ruff_fixed)

        # 2. 统计结果
        ruff_fixable = [f for f in fixable if self._is_ruff_fixable(f)]
        llm_fixable = [f for f in fixable if not self._is_ruff_fixable(f)]

        fixed_count = len(ruff_fixed)
        skipped = [
            {
                "file_path": f.get("file_path", ""),
                "rule_id": f.get("rule_id", ""),
                "message": f.get("message", ""),
                "reason": "需要 LLM 辅助修复（暂未实现）" if not self._is_ruff_fixable(f) else "Ruff 未修复到此文件",
            }
            for f in fixable
            if f.get("file_path") not in ruff_fixed
        ]

        summary = (
            f"共 {len(fixable)} 个可修复项："
            f"{len(ruff_fixable)} 个 Ruff 可修复（已修复 {fixed_count} 个文件），"
            f"{len(llm_fixable)} 个需要人工处理"
        )

        logger.info("自动修复完成", patches=len(patches), fixed=len(fixed_files), skipped=len(skipped))
        return {
            "patches": patches,
            "fixed_files": sorted(fixed_files),
            "skipped": skipped,
            "summary": summary,
        }

    def _is_ruff_fixable(self, finding: dict) -> bool:
        """判断 finding 是否可由 Ruff 修复"""
        rule = finding.get("rule_id", "")
        # Ruff 可自动修复的规则前缀
        ruff_fixable_prefixes = ("F401", "F841", "I", "E", "W", "UP", "C4", "SIM", "RUF")
        return any(rule.startswith(p) for p in ruff_fixable_prefixes)

    def _run_ruff_fix(
        self,
        path: Path,
        apply: bool = False,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """运行 Ruff 自动修复并生成 diff

        Returns:
            (patches, fixed_file_paths)
        """
        if apply:
            # 直接修复模式：ruff check --fix
            cmd = ["ruff", "check", "--fix", "--no-cache", str(path)]
        else:
            # 预览模式：ruff check --fix --diff（输出 diff 不修改文件）
            cmd = ["ruff", "check", "--fix", "--diff", "--no-cache", str(path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(path),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Ruff 修复失败", error=str(e))
            return [], set()

        patches = []
        fixed_files = set()

        if apply:
            # 修复模式：重新检查哪些文件被修改了
            # 通过 ruff check --output-format json 检查剩余问题
            check_result = subprocess.run(
                ["ruff", "check", "--output-format", "json", "--no-cache", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(path),
            )
            # 从 stdout 获取 diff（如果有）
            if result.stdout.strip():
                patches.append({
                    "type": "ruff",
                    "diff": result.stdout,
                    "files": self._extract_files_from_diff(result.stdout),
                })
                fixed_files.update(self._extract_files_from_diff(result.stdout))
        else:
            # 预览模式：diff 在 stdout
            diff_output = result.stdout
            if diff_output.strip():
                patches.append({
                    "type": "ruff",
                    "diff": diff_output,
                    "files": self._extract_files_from_diff(diff_output),
                })
                fixed_files.update(self._extract_files_from_diff(diff_output))

        return patches, fixed_files

    def _run_ruff_fix_with_diff(
        self,
        path: Path,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """运行 Ruff 修复并返回 diff（不修改原文件）

        复制到临时目录执行修复，然后对比生成 diff。
        """
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="autofix_")
            tmp_path = Path(tmp_dir)

            # 复制项目到临时目录
            for item in path.rglob("*"):
                if item.is_file() and "/__pycache__/" not in str(item) and "/.git/" not in str(item):
                    rel = item.relative_to(path)
                    dest = tmp_path / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(item, dest)
                    except (OSError, shutil.Error):
                        continue

            # 在临时目录运行修复
            result = subprocess.run(
                ["ruff", "check", "--fix", "--no-cache", "."],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=tmp_dir,
            )

            # 对比差异
            patches = []
            fixed_files = set()

            for py_file in tmp_path.rglob("*.py"):
                rel = str(py_file.relative_to(tmp_path))
                original = path / rel
                if not original.exists():
                    continue

                original_content = original.read_text(errors="ignore")
                fixed_content = py_file.read_text(errors="ignore")

                if original_content != fixed_content:
                    diff = difflib.unified_diff(
                        original_content.splitlines(keepends=True),
                        fixed_content.splitlines(keepends=True),
                        fromfile=f"a/{rel}",
                        tofile=f"b/{rel}",
                    )
                    diff_str = "".join(diff)
                    if diff_str:
                        patches.append({
                            "type": "ruff",
                            "file": rel,
                            "diff": diff_str,
                        })
                        fixed_files.add(rel)

            return patches, fixed_files

        except Exception as e:
            logger.warning("Ruff 修复（diff 模式）失败", error=str(e))
            return [], set()
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _extract_files_from_diff(diff_text: str) -> set[str]:
        """从 unified diff 中提取修改的文件路径"""
        files = set()
        for line in diff_text.splitlines():
            if line.startswith("--- a/") or line.startswith("+++ b/"):
                fp = line[6:].strip()
                if fp:
                    files.add(fp)
        return files

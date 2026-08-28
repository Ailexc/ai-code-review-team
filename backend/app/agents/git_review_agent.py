"""Git 审查 Agent — 提交规范 + 分支策略 + 贡献统计 + LLM 点评

检测维度：
1. 提交规范 — Conventional Commits 格式检查
2. 分支策略 — 分支命名规范、主分支保护
3. 贡献统计 — 活跃度、文件热点、提交频率
4. 提交消息质量 — LLM 语义点评
"""

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()

# Conventional Commits 正则
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\(.+\))?(!)?:\s.+"
)

# 分支命名规范（允许 main, master, develop 或 type/description 格式）
BRANCH_PATTERN = re.compile(
    r"^(main|master|develop)$|"
    r"^(feature|fix|hotfix|release|chore|docs)/[\w\-\.]+$"
)

# Commit 类型中文说明
COMMIT_TYPE_LABELS = {
    "feat": "新功能",
    "fix": "修复",
    "docs": "文档",
    "style": "格式",
    "refactor": "重构",
    "perf": "性能",
    "test": "测试",
    "build": "构建",
    "ci": "CI",
    "chore": "杂项",
    "revert": "回滚",
}

# LLM 提交分析提示词
GIT_PROMPT = """你是一个 Git 工作流专家。请分析以下 Git 仓库信息，找出可改进之处。

仓库信息:
{repo_info}

最近提交历史:
{commit_log}

分支列表:
{branches}

请用 JSON 格式返回分析结果:
```json
{{
    "findings": [
        {{
            "rule_id": "GIT-001",
            "severity": "warning/suggestion/nitpick",
            "message": "简短描述问题",
            "file_path": "",
            "line_number": null,
            "code_snippet": "",
            "suggestion": "改进建议"
        }}
    ]
}}
```

审查重点:
1. 提交规范 — 是否遵循 Conventional Commits（feat/fix/docs/...）
2. 提交消息质量 — 是否清晰描述变更内容（过短、含糊、无意义）
3. 分支策略 — 分支命名是否规范，是否有长期未合并的分支
4. 提交粒度 — 是否单次提交包含过多不相关变更
5. 安全 — 是否有敏感信息泄露（密码、token、密钥）

注意:
1. 只返回 JSON，不要有其他内容
2. 如果没有问题，返回空数组: {{"findings": []}}
3. severity 分为: warning (违反规范), suggestion (可改进), nitpick (细节)"""


class GitReviewAgent(BaseAgent):
    """Git 审查 Agent — 提交规范 + 分支策略 + 贡献统计"""

    name = "git_review"
    description = "Git 审查（提交规范 + 分支策略 + 贡献统计 + LLM 点评）"

    async def analyze(
        self,
        project_path: str,
        file_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """运行 Git 审查"""
        path = Path(project_path)
        if not path.exists():
            logger.warning("项目路径不存在", path=project_path)
            return []

        # 检查是否为 Git 仓库
        if not (path / ".git").exists():
            logger.info("非 Git 仓库，跳过 Git 审查", path=project_path)
            return []

        findings = []

        # 可观测性：确定性扫描子步骤记录
        import time as _time
        from app.services.review_steps import review_step_recorder

        # 1. 提交规范检查
        _t0 = _time.monotonic()
        try:
            commit_findings = self._check_commit_conventions(path)
            findings.extend(commit_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="git_commit_check",
                    action_text=f"🔍 提交规范检查：命中 {len(commit_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(commit_findings)},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("提交规范检查失败", error=str(e))

        # 2. 分支策略检查
        _t0 = _time.monotonic()
        try:
            branch_findings = self._check_branch_strategy(path)
            findings.extend(branch_findings)
            _dur = int((_time.monotonic() - _t0) * 1000)
            try:
                await review_step_recorder.record_tool_substep(
                    agent_name=self.name,
                    node_type="git_branch_check",
                    action_text=f"🔍 分支策略检查：命中 {len(branch_findings)} 条（{_dur / 1000:.1f}s）",
                    duration_ms=_dur,
                    detail={"findings": len(branch_findings)},
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning("分支策略检查失败", error=str(e))

        # 3. 贡献统计
        try:
            findings.extend(self._analyze_contributions(path))
        except Exception as e:
            logger.warning("贡献统计失败", error=str(e))

        # 4. LLM 点评
        try:
            llm_findings = await self._run_llm_analysis(path)
            findings.extend(llm_findings)
        except Exception as e:
            logger.warning("LLM Git 分析失败", error=str(e))

        # 去重
        seen = set()
        unique = []
        for f in findings:
            key = (f.get("rule_id"), f.get("message", "")[:50])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("Git 审查完成", path=project_path, findings=len(unique))
        return unique

    def _run_git(self, path: Path, args: list[str], timeout: int = 30) -> str:
        """执行 git 命令"""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(path),
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    # ──────────────────────────────────────────────────────────────
    # 提交规范检查
    # ──────────────────────────────────────────────────────────────

    def _check_commit_conventions(self, path: Path) -> list[dict[str, Any]]:
        """检查最近 50 条提交是否遵循 Conventional Commits"""
        findings = []
        log = self._run_git(path, [
            "log", "--format=%H|%s|%an|%ad", "--date=short", "-50",
        ])
        if not log:
            return []

        non_conventional = []
        bad_messages = []

        for line in log.splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            commit_hash, subject, author, date = parts

            if not CONVENTIONAL_RE.match(subject):
                non_conventional.append(subject)

            # 检查提交消息质量
            if len(subject.split(":")[-1].strip()) < 5:
                bad_messages.append(subject)

        # 非规范提交占比
        total = len(log.splitlines())
        if total > 0 and non_conventional:
            ratio = len(non_conventional) / total
            if ratio > 0.5:
                findings.append({
                    "rule_id": "GIT-CONVENTIONAL",
                    "severity": "warning",
                    "message": f"近 50 条提交中 {len(non_conventional)}/{total} 条未遵循 Conventional Commits 规范",
                    "file_path": "",
                    "line_start": None,
                    "code_snippet": "\n".join(non_conventional[:5]),
                    "suggestion": "使用 Conventional Commits 格式：`type(scope): description`，如 `feat(auth): add login endpoint`",
                })
            elif ratio > 0.2:
                findings.append({
                    "rule_id": "GIT-CONVENTIONAL",
                    "severity": "suggestion",
                    "message": f"近 50 条提交中 {len(non_conventional)}/{total} 条未遵循 Conventional Commits 规范",
                    "file_path": "",
                    "line_start": None,
                    "code_snippet": "\n".join(non_conventional[:3]),
                    "suggestion": "建议统一使用 Conventional Commits 格式",
                })

        # 模糊提交消息
        if bad_messages:
            findings.append({
                "rule_id": "GIT-MESSAGE",
                "severity": "suggestion",
                "message": f"有 {len(bad_messages)} 条提交消息过短或含糊",
                "file_path": "",
                "line_start": None,
                "code_snippet": "\n".join(bad_messages[:5]),
                "suggestion": "提交消息应清晰描述变更内容和动机，建议至少 10 个字符",
            })

        return findings

    # ──────────────────────────────────────────────────────────────
    # 分支策略检查
    # ──────────────────────────────────────────────────────────────

    def _check_branch_strategy(self, path: Path) -> list[dict[str, Any]]:
        """检查分支命名规范"""
        findings = []

        # 获取本地分支
        branches_output = self._run_git(path, ["branch", "--format=%(refname:short)"])
        if not branches_output:
            return []

        branches = [b.strip() for b in branches_output.splitlines() if b.strip()]
        non_standard = []

        for branch in branches:
            # 跳过 main/master/develop
            if branch in ("main", "master", "develop", "HEAD"):
                continue
            if not BRANCH_PATTERN.match(branch):
                non_standard.append(branch)

        if non_standard:
            findings.append({
                "rule_id": "GIT-BRANCH",
                "severity": "nitpick",
                "message": f"有 {len(non_standard)} 个分支命名不符合规范",
                "file_path": "",
                "line_start": None,
                "code_snippet": "\n".join(non_standard[:5]),
                "suggestion": "分支命名建议使用 `type/description` 格式，如 `feature/user-auth`、`fix/login-bug`",
            })

        # 检查长期未合并的分支（超过 30 天）
        stale = self._find_stale_branches(path, branches)
        if stale:
            findings.append({
                "rule_id": "GIT-STALE",
                "severity": "suggestion",
                "message": f"有 {len(stale)} 个分支超过 30 天未更新",
                "file_path": "",
                "line_start": None,
                "code_snippet": "\n".join([f"{b} ({d}天前)" for b, d in stale[:5]]),
                "suggestion": "定期清理已合并或废弃的分支，保持仓库整洁",
            })

        return findings

    def _find_stale_branches(self, path: Path, branches: list[str]) -> list[tuple[str, int]]:
        """找出超过 30 天未更新的分支"""
        stale = []
        for branch in branches:
            if branch in ("main", "master", "develop"):
                continue
            last_commit = self._run_git(path, [
                "log", "-1", "--format=%ct", branch,
            ])
            if last_commit:
                try:
                    import time
                    days = int((time.time() - int(last_commit)) / 86400)
                    if days > 30:
                        stale.append((branch, days))
                except (ValueError, TypeError):
                    pass
        return stale

    # ──────────────────────────────────────────────────────────────
    # 贡献统计
    # ──────────────────────────────────────────────────────────────

    def _analyze_contributions(self, path: Path) -> list[dict[str, Any]]:
        """分析贡献模式"""
        findings = []

        # 最近 30 天的提交频率
        log = self._run_git(path, [
            "log", "--format=%ad", "--date=short", "--since=30 days ago",
        ])
        if log:
            dates = [line.strip() for line in log.splitlines() if line.strip()]
            if dates:
                commit_count = len(dates)
                active_days = len(set(dates))

                # 高频提交但低活跃天数（可能一次性大量提交）
                if commit_count > 50 and active_days < 5:
                    findings.append({
                        "rule_id": "GIT-BURST",
                        "severity": "suggestion",
                        "message": f"近 30 天 {commit_count} 次提交集中在 {active_days} 天内（突击提交模式）",
                        "file_path": "",
                        "line_start": None,
                        "code_snippet": "",
                        "suggestion": "建议均匀分布提交，避免大量变更集中在少数几天，便于代码审查和问题定位",
                    })

        # 文件热点 — 被修改最多的文件
        hotspot_log = self._run_git(path, [
            "log", "--format=", "--name-only", "--since=90 days ago",
        ])
        if hotspot_log:
            files = [f.strip() for f in hotspot_log.splitlines() if f.strip()]
            counter = Counter(files)
            hotspots = counter.most_common(5)
            if hotspots and hotspots[0][1] > 20:
                snippet = "\n".join([f"  {f}: {c}次修改" for f, c in hotspots])
                findings.append({
                    "rule_id": "GIT-HOTSPOT",
                    "severity": "suggestion",
                    "message": f"近 90 天热点文件（修改频率最高的文件可能是设计问题）",
                    "file_path": hotspots[0][0],
                    "line_start": None,
                    "code_snippet": snippet,
                    "suggestion": "高频修改的文件可能存在职责不清或耦合过重的问题，建议考虑拆分或重构",
                })

        return findings

    # ──────────────────────────────────────────────────────────────
    # LLM 分析
    # ──────────────────────────────────────────────────────────────

    async def _run_llm_analysis(self, path: Path) -> list[dict[str, Any]]:
        """使用 LLM 进行 Git 工作流分析"""
        try:
            from app.agents.llm_client import get_active_llm_config, llm_complete, parse_json_object

            config = await get_active_llm_config()
            if not config:
                return []

            # 收集仓库信息
            repo_info = self._collect_repo_info(path)
            commit_log = self._run_git(path, [
                "log", "--format=%h|%s|%an|%ad", "--date=short", "-20",
            ])
            branches = self._run_git(path, ["branch", "-a", "--format=%(refname:short)"])

            prompt = GIT_PROMPT.format(
                repo_info=repo_info,
                commit_log=commit_log or "(无提交历史)",
                branches=branches or "(无分支信息)",
            )

            reply = await llm_complete(config, prompt)
            data = parse_json_object(reply)
            if not data or "findings" not in data:
                return []

            results = []
            for f in data["findings"]:
                results.append({
                    "rule_id": f.get("rule_id", "LLM-GIT"),
                    "severity": f.get("severity", "suggestion"),
                    "message": f.get("message", ""),
                    "file_path": f.get("file_path", ""),
                    "line_start": f.get("line_number"),
                    "code_snippet": f.get("code_snippet", ""),
                    "suggestion": f.get("suggestion", ""),
                })

            logger.info("LLM Git 分析完成", findings=len(results))
            return results

        except ImportError:
            return []

    def _collect_repo_info(self, path: Path) -> str:
        """收集仓库基本信息"""
        info_parts = []

        # 远程仓库
        remote = self._run_git(path, ["remote", "-v"])
        if remote:
            info_parts.append(f"远程仓库:\n{remote}")

        # 当前分支
        branch = self._run_git(path, ["branch", "--show-current"])
        if branch:
            info_parts.append(f"当前分支: {branch}")

        # 总提交数
        total = self._run_git(path, ["rev-list", "--count", "HEAD"])
        if total:
            info_parts.append(f"总提交数: {total}")

        # 贡献者
        authors = self._run_git(path, [
            "shortlog", "-sn", "--all", "--no-merges",
        ])
        if authors:
            info_parts.append(f"贡献者:\n{authors}")

        return "\n\n".join(info_parts) if info_parts else "(无法获取仓库信息)"

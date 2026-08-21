"""审查服务 — 编排审查流程（多 Agent 并行 + 结果聚合）"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.models.finding import Finding
from app.models.project import Project
from app.agents.security_agent import SecurityAgent
from app.agents.code_style_agent import CodeStyleAgent
from app.agents.dependency_agent import DependencyAgent
from app.agents.test_coverage_agent import TestCoverageAgent
from app.services.health import compute_health_score
from app.services.progress import progress_emitter

logger = structlog.get_logger()

# Agent 注册表：review_type 片段 → (Agent 类, agent_name, category)
AGENT_REGISTRY = {
    "security": (SecurityAgent, "security", "security"),
    "code_style": (CodeStyleAgent, "code_style", "code_style"),
    "dependency": (DependencyAgent, "dependency", "dependency"),
    "test_coverage": (TestCoverageAgent, "test_coverage", "test_coverage"),
}


class ReviewService:
    """审查服务 — 协调各 Agent 执行审查并汇总结果"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _resolve_agents(self, review_type: str) -> list[tuple[Any, str, str]]:
        """根据审查类型解析需要运行的 Agent 列表"""
        if review_type == "full":
            return list(AGENT_REGISTRY.values())
        if review_type in AGENT_REGISTRY:
            return [AGENT_REGISTRY[review_type]]
        # 未知类型：默认只跑安全审查
        logger.warning("未知审查类型，回退到 security", review_type=review_type)
        return [AGENT_REGISTRY["security"]]

    async def run_review(
        self,
        project: Project,
        review_type: str = "full",
        trigger_type: str = "manual",
        file_paths: list[str] | None = None,
        existing_review_id: str | None = None,
    ) -> Review:
        """执行一次完整审查（多 Agent 并行）

        Args:
            project: 项目对象
            review_type: 审查类型 (full / security / code_style / dependency / test_coverage)
            trigger_type: 触发方式 (manual / cli / web_trigger)
            file_paths: 指定审查的文件列表，None 则扫描项目目录
            existing_review_id: 若由 run-async 预创建，则复用该审查记录
        """
        # 创建或复用审查记录
        if existing_review_id:
            result = await self.db.execute(select(Review).where(Review.id == existing_review_id))
            review = result.scalar_one_or_none()
            if not review:
                review = Review(
                    project_id=project.id,
                    trigger_type=trigger_type,
                    review_type=review_type,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                self.db.add(review)
                await self.db.flush()
            else:
                review.status = "running"
                review.started_at = datetime.now(timezone.utc)
                await self.db.flush()
        else:
            review = Review(
                project_id=project.id,
                trigger_type=trigger_type,
                review_type=review_type,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(review)
            await self.db.flush()
        logger.info("开始审查", review_id=review.id, project=project.name, type=review_type)
        await progress_emitter.emit(review.id, "review_started", {
            "review_type": review_type, "project": project.name,
        })

        start_time = time.monotonic()
        all_findings: list[Finding] = []

        try:
            agents = self._resolve_agents(review_type)

            # 并行执行各 Agent
            async def _run_one(agent_cls, agent_name: str, category: str) -> list[dict[str, Any]]:
                agent = agent_cls()
                logger.info("Agent 开始", review_id=review.id, agent=agent_name)
                await progress_emitter.emit(review.id, "agent_started", {"agent": agent_name})
                findings = await agent.analyze(
                    project_path=project.path,
                    file_paths=file_paths,
                )
                logger.info("Agent 完成", review_id=review.id, agent=agent_name, count=len(findings))
                await progress_emitter.emit(review.id, "agent_completed", {
                    "agent": agent_name, "findings": len(findings),
                })
                return findings

            results = await asyncio.gather(
                *[_run_one(cls, name, cat) for cls, name, cat in agents]
            )

            # 聚合入库
            for (cls, agent_name, category), findings in zip(agents, results):
                for f in findings:
                    finding = Finding(
                        review_id=review.id,
                        agent_name=agent_name,
                        category=category,
                        severity=f.get("severity", "warning"),
                        message=f.get("message", ""),
                        description=f.get("message", ""),
                        file_path=f.get("file_path", ""),
                        line_number=f.get("line_start"),
                        code_snippet=f.get("code_snippet", ""),
                        suggestion=f.get("suggestion", ""),
                        is_auto_fixable=bool(f.get("is_auto_fixable", False)),
                        fix_suggestion=f.get("fix_suggestion"),
                    )
                    self.db.add(finding)
                    all_findings.append(finding)

            # 更新审查记录
            elapsed = int(time.monotonic() - start_time)
            review.status = "completed"
            review.completed_at = datetime.now(timezone.utc)
            review.duration_seconds = elapsed
            review.total_findings = len(all_findings)
            review.critical_count = sum(1 for f in all_findings if f.severity == "critical")
            review.warning_count = sum(1 for f in all_findings if f.severity == "warning")
            review.suggestion_count = sum(1 for f in all_findings if f.severity == "suggestion")
            review.nitpick_count = sum(1 for f in all_findings if f.severity == "nitpick")
            review.summary = self._generate_summary(review)
            review.health_score_snapshot = compute_health_score(review, all_findings)
            project.health_score = review.health_score_snapshot

            await self.db.flush()
            logger.info(
                "审查完成",
                review_id=review.id,
                findings=review.total_findings,
                duration=f"{elapsed}s",
                agents=[a[1] for a in agents],
                health_score=review.health_score_snapshot,
            )
            await progress_emitter.emit(review.id, "review_completed", {
                "total_findings": review.total_findings,
                "critical": review.critical_count,
                "warning": review.warning_count,
                "suggestion": review.suggestion_count,
                "nitpick": review.nitpick_count,
                "health_score": review.health_score_snapshot,
                "duration_seconds": elapsed,
                "summary": review.summary,
            })

        except Exception as e:
            review.status = "failed"
            review.completed_at = datetime.now(timezone.utc)
            review.duration_seconds = int(time.monotonic() - start_time)
            review.summary = f"审查失败: {e}"
            await self.db.flush()
            logger.error("审查失败", review_id=review.id, error=str(e))
            await progress_emitter.emit(review.id, "review_failed", {"error": str(e)})
            raise

        return review

    def _generate_summary(self, review: Review) -> str:
        """生成审查摘要"""
        parts = []
        if review.critical_count:
            parts.append(f"🔴 {review.critical_count} 个严重问题")
        if review.warning_count:
            parts.append(f"🟡 {review.warning_count} 个警告")
        if review.suggestion_count:
            parts.append(f"🔵 {review.suggestion_count} 个建议")
        if review.nitpick_count:
            parts.append(f"⚪ {review.nitpick_count} 个细节")
        if not parts:
            return "✅ 未发现问题"
        return f"发现 {review.total_findings} 个问题：" + "，".join(parts)

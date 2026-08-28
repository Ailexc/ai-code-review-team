"""审查服务 — 服务层（DB 持久化 / 指标 / 进度事件），编排委托 CrewAI ReviewFlow

编排方式（路线焊死）：CrewAI Flows + Crews 双层架构（外层 Flow 确定性编排 +
内层 6 个 Crew 自主协作）。本服务**不再承担任何编排职责**（无 asyncio.gather），
只负责：
1. 创建 / 复用 Review 记录；
2. 委托 ReviewFlow 执行审查；
3. 将 findings_by_agent 持久化、统计、生成摘要、记录指标与进度事件。
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.review_flow import run_review_flow
from app.models.review import Review
from app.models.finding import Finding
from app.models.project import Project
from app.services.health import compute_health_score
from app.services.progress import progress_emitter
from app.services.metrics import metrics

logger = structlog.get_logger()

# Agent 注册表：agent_name → category（与 crew_factory.AGENT_PROFILES 对齐）
AGENT_REGISTRY = {
    "security": "security",
    "code_style": "code_style",
    "dependency": "dependency",
    "test_coverage": "test_coverage",
    "performance": "performance",
    "git_review": "git_review",
}


class ReviewService:
    """审查服务 — 服务层门面：委托 CrewAI ReviewFlow 执行，负责持久化与统计"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_review(
        self,
        project: Project,
        review_type: str = "full",
        trigger_type: str = "manual",
        file_paths: list[str] | None = None,
        existing_review_id: str | None = None,
        orchestration_mode: str = "parallel",
    ) -> Review:
        """执行一次完整审查（CrewAI Flows + Crews 双层架构）

        Args:
            project: 项目对象
            review_type: 审查类型 (full / security / code_style / dependency / test_coverage / performance / git_review)
            trigger_type: 触发方式 (manual / cli / web_trigger / incremental)
            file_paths: 指定审查的文件列表，None 则扫描项目目录
            existing_review_id: 若由 run-async 预创建，则复用该审查记录
            orchestration_mode: 编排模式 parallel（默认）/ hierarchical（manager 派发，学习对比）
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
                    orchestration_mode=orchestration_mode,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                self.db.add(review)
                await self.db.flush()
                await self.db.commit()  #尽早提交，释放 SQLite 写锁（审查期间供 review_steps 等独立 session 写入）
            else:
                review.status = "running"
                review.started_at = datetime.now(timezone.utc)
                await self.db.flush()
                await self.db.commit()
        else:
            review = Review(
                project_id=project.id,
                trigger_type=trigger_type,
                review_type=review_type,
                orchestration_mode=orchestration_mode,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(review)
            await self.db.flush()
            await self.db.commit()  #尽早提交，释放 SQLite 写锁
        logger.info("开始审查", review_id=review.id, project=project.name, type=review_type)
        await progress_emitter.emit(review.id, "review_started", {
            "review_type": review_type, "project": project.name,
        })

        start_time = time.monotonic()
        all_findings: list[Finding] = []

        try:
            # ===== 编排：CrewAI Flows + Crews 双层架构（生产主路径）=====
            # 外层 Flow 负责节点流转与并行调度（6 个内层 Crew 并行执行），
            # 进度事件（flow_node_*/agent_*）由 Flow 内部经 progress_emitter 发布。
            state = await run_review_flow(
                project_path=project.path,
                review_type=review_type,
                file_paths=file_paths,
                project_name=project.name,
                review_id=review.id,
                orchestration_mode=orchestration_mode,
            )

            # ===== 持久化：findings_by_agent → Finding 表 =====
            for agent_name, findings in state.findings_by_agent.items():
                category = agent_name
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

            # ===== 统计与摘要 =====
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
            metrics.record_review(review_type, "completed", elapsed)
            # 审计日志
            metrics.record_audit("review_completed", {
                "review_id": review.id,
                "project": project.name,
                "review_type": review_type,
                "findings": review.total_findings,
                "duration_s": elapsed,
                "health_score": review.health_score_snapshot,
            })
            logger.info(
                "审查完成",
                review_id=review.id,
                findings=review.total_findings,
                duration=f"{elapsed}s",
                agents=list(state.findings_by_agent.keys()),
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
            metrics.record_review(review_type, "failed", review.duration_seconds)
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

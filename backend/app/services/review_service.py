"""审查服务 — 编排审查流程"""

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.models.finding import Finding
from app.models.project import Project
from app.agents.security_agent import SecurityAgent

logger = structlog.get_logger()


class ReviewService:
    """审查服务 — 协调各 Agent 执行审查并汇总结果"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.security_agent = SecurityAgent()

    async def run_review(
        self,
        project: Project,
        review_type: str = "full",
        trigger_type: str = "manual",
        file_paths: list[str] | None = None,
    ) -> Review:
        """执行一次完整审查

        Args:
            project: 项目对象
            review_type: 审查类型 (full / security / code_style)
            trigger_type: 触发方式 (manual / cli / web_trigger)
            file_paths: 指定审查的文件列表，None 则扫描项目目录
        """
        # 创建审查记录
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

        start_time = time.monotonic()
        all_findings = []

        try:
            # 根据审查类型执行不同 Agent
            if review_type in ("full", "security"):
                findings = await self.security_agent.analyze(
                    project_path=project.path,
                    file_paths=file_paths,
                )
                for f in findings:
                    finding = Finding(
                        review_id=review.id,
                        agent_name="security",
                        category="security",
                        severity=f.get("severity", "warning"),
                        message=f.get("message", ""),
                        description=f.get("message", ""),
                        file_path=f.get("file_path", ""),
                        line_number=f.get("line_start"),
                        code_snippet=f.get("code_snippet", ""),
                        suggestion=f.get("suggestion", ""),
                    )
                    self.db.add(finding)
                    all_findings.append(finding)

            # TODO: code_style / dependency / test_coverage agents

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

            await self.db.flush()
            logger.info(
                "审查完成",
                review_id=review.id,
                findings=review.total_findings,
                duration=f"{elapsed}s",
            )

        except Exception as e:
            review.status = "failed"
            review.completed_at = datetime.now(timezone.utc)
            review.duration_seconds = int(time.monotonic() - start_time)
            review.summary = f"审查失败: {e}"
            await self.db.flush()
            logger.error("审查失败", review_id=review.id, error=str(e))
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

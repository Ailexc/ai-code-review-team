"""系统管理 API"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.review import Review
from app.models.finding import Finding

router = APIRouter()


@router.get("/health")
async def health_check():
    """系统健康检查"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """系统统计数据（仪表盘用）"""
    project_total = (await db.execute(select(func.count(Project.id)))).scalar() or 0
    review_total = (await db.execute(select(func.count(Review.id)))).scalar() or 0

    finding_total = (await db.execute(select(func.count(Finding.id)))).scalar() or 0
    critical = (await db.execute(
        select(func.count(Finding.id)).where(Finding.severity == "critical")
    )).scalar() or 0
    warning = (await db.execute(
        select(func.count(Finding.id)).where(Finding.severity == "warning")
    )).scalar() or 0
    suggestion = (await db.execute(
        select(func.count(Finding.id)).where(Finding.severity == "suggestion")
    )).scalar() or 0
    fixed = (await db.execute(
        select(func.count(Finding.id)).where(Finding.status == "fixed")
    )).scalar() or 0

    # 最近审查
    recent = (await db.execute(
        select(Review).order_by(Review.created_at.desc()).limit(10)
    )).scalars().all()

    return {
        "projects_total": project_total,
        "reviews_total": review_total,
        "findings_total": finding_total,
        "findings_critical": critical,
        "findings_warning": warning,
        "findings_suggestion": suggestion,
        "findings_fixed": fixed,
        "recent_reviews": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "review_type": r.review_type,
                "status": r.status,
                "total_findings": r.total_findings,
                "critical_count": r.critical_count,
                "warning_count": r.warning_count,
                "created_at": r.created_at,
            }
            for r in recent
        ],
    }

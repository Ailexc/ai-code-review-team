"""审查管理 API"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog

from app.core.database import get_db
from app.models.review import Review
from app.models.finding import Finding
from app.models.project import Project
from app.schemas.review import ReviewCreate, ReviewResponse
from app.services.review_service import ReviewService
from app.services.report_generator import ReportGenerator

logger = structlog.get_logger()
router = APIRouter()


@router.get("", response_model=list[ReviewResponse])
async def list_reviews(
    project_id: str = None,
    db: AsyncSession = Depends(get_db),
):
    """获取审查列表"""
    query = select(Review)
    if project_id:
        query = query.where(Review.project_id == project_id)
    query = query.order_by(Review.created_at.desc())

    result = await db.execute(query)
    reviews = result.scalars().all()
    return [ReviewResponse.model_validate(r) for r in reviews]


@router.post("", response_model=ReviewResponse, status_code=201)
async def create_review(
    data: ReviewCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建审查记录（仅创建，不执行分析）"""
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="项目不存在")

    review = Review(**data.model_dump())
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return ReviewResponse.model_validate(review)


@router.post("/run", response_model=ReviewResponse, status_code=201)
async def run_review(
    project_id: str,
    review_type: str = "full",
    trigger_type: str = "manual",
    db: AsyncSession = Depends(get_db),
):
    """执行审查 — 触发安全扫描并返回结果"""
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    service = ReviewService(db)
    try:
        review = await service.run_review(
            project=project,
            review_type=review_type,
            trigger_type=trigger_type,
        )
        return ReviewResponse.model_validate(review)
    except Exception as e:
        logger.error("审查执行失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"审查执行失败: {e}")


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取审查详情"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="审查不存在")
    return ReviewResponse.model_validate(review)


@router.get("/{review_id}/report", response_class=PlainTextResponse)
async def get_review_report(
    review_id: str,
    db: AsyncSession = Depends(get_db),
):
    """下载审查报告（Markdown 格式）"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="审查不存在")

    # 获取项目信息
    project_result = await db.execute(select(Project).where(Project.id == review.project_id))
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown"

    # 获取发现列表
    findings_result = await db.execute(
        select(Finding).where(Finding.review_id == review_id).order_by(Finding.severity)
    )
    findings = findings_result.scalars().all()

    # 生成报告
    generator = ReportGenerator()
    report = generator.generate(review, findings, project_name)

    return PlainTextResponse(
        content=report,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=review-{review_id[:8]}.md"
        }
    )

"""审查发现管理 API"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

import structlog

from app.core.database import get_db
from app.models.finding import Finding
from app.schemas.finding import FindingResponse, FindingStatusUpdate

logger = structlog.get_logger()
router = APIRouter()


@router.get("", response_model=list[FindingResponse])
async def list_findings(
    review_id: str = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取发现列表"""
    query = select(Finding)
    if review_id:
        query = query.where(Finding.review_id == review_id)
    if severity:
        query = query.where(Finding.severity == severity)
    if category:
        query = query.where(Finding.category == category)
    if status:
        query = query.where(Finding.status == status)
    query = query.order_by(Finding.created_at.desc())

    result = await db.execute(query)
    findings = result.scalars().all()
    return [FindingResponse.model_validate(f) for f in findings]


@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(
    finding_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取发现详情"""
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="发现不存在")
    return FindingResponse.model_validate(finding)


@router.put("/{finding_id}/status", response_model=FindingResponse)
async def update_finding_status(
    finding_id: str,
    data: FindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新发现状态（open / acknowledged / fixed）"""
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="发现不存在")

    old_status = finding.status
    finding.status = data.status
    await db.flush()
    logger.info("发现状态更新", finding_id=finding_id, old_status=old_status, new_status=data.status)

    # 应用规则反馈（PR 历史学习）
    try:
        from app.services.rule_miner import rule_miner
        await rule_miner.apply_feedback(finding_id, data.status)
    except Exception as e:
        logger.warning("规则反馈应用失败", error=str(e))

    return FindingResponse.model_validate(finding)

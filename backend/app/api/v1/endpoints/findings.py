"""审查发现管理 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.models.finding import Finding
from app.schemas.finding import FindingResponse

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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="发现不存在")
    return FindingResponse.model_validate(finding)

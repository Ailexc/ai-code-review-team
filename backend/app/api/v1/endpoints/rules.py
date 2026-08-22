"""审查规则 API — 管理从历史审查中学习的规则"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.core.database import get_db
from app.models.review_rule import ReviewRule
from app.services.rule_miner import rule_miner

logger = structlog.get_logger()
router = APIRouter()


@router.get("")
async def list_rules(
    agent_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取规则列表"""
    query = select(ReviewRule).order_by(ReviewRule.weight.desc())
    if agent_name:
        query = query.where(ReviewRule.agent_name == agent_name)
    result = await db.execute(query)
    rules = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "rule_type": r.rule_type,
            "agent_name": r.agent_name,
            "severity": r.severity,
            "pattern": r.pattern,
            "confidence": r.confidence,
            "occurrence_count": r.occurrence_count,
            "weight": r.weight,
            "is_enabled": r.is_enabled,
            "source": r.source,
            "created_at": r.created_at,
        }
        for r in rules
    ]


@router.post("/mine")
async def mine_rules(min_occurrences: int = 3):
    """从历史审查记录挖掘规则"""
    new_rules = await rule_miner.mine_from_history(min_occurrences)
    return {
        "mined": len(new_rules),
        "message": f"挖掘到 {len(new_rules)} 条新规则",
    }


@router.put("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用规则"""
    result = await db.execute(select(ReviewRule).where(ReviewRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.is_enabled = not rule.is_enabled
    await db.commit()
    return {"id": rule.id, "is_enabled": rule.is_enabled}


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除规则"""
    result = await db.execute(select(ReviewRule).where(ReviewRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.delete(rule)
    await db.commit()
    return {"deleted": rule_id}
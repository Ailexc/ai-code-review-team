"""语义 Diff API — 分析 Git 变更的结构化影响和意图"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.core.database import get_db
from app.models.project import Project
from app.services.semantic_diff import semantic_diff
from app.services.intent_analysis import analyze_intent

logger = structlog.get_logger()
router = APIRouter()


@router.get("/{project_id}/diff")
async def get_semantic_diff(
    project_id: str,
    base: str = "HEAD~1",
    head: str = "HEAD",
    db: AsyncSession = Depends(get_db),
):
    """分析项目 Git 变更的语义影响"""
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    diff_result = semantic_diff.analyze(project.path, base=base, head=head)
    return diff_result


@router.get("/{project_id}/diff/intent")
async def get_diff_intent(
    project_id: str,
    base: str = "HEAD~1",
    head: str = "HEAD",
    db: AsyncSession = Depends(get_db),
):
    """分析 Git 变更的意图（LLM 增强）"""
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    diff_result = semantic_diff.analyze(project.path, base=base, head=head)
    intent = await analyze_intent(diff_result)
    return {
        "diff": diff_result,
        "intent": intent,
    }
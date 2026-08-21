"""审查管理 API"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, HTMLResponse
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
    """执行审查 — 触发安全扫描并返回结果（同步，阻塞至完成）"""
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


@router.post("/run-incremental", response_model=ReviewResponse, status_code=201)
async def run_incremental_review(
    project_id: str,
    review_type: str = "full",
    base: str = "HEAD~1",
    head: str = "HEAD",
    db: AsyncSession = Depends(get_db),
):
    """增量审查 — 只审查 Git diff 变更文件（贴合 PR 场景，控制 token 成本）"""
    from app.services.diff_parser import get_changed_files

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    diff = get_changed_files(project.path, base=base, head=head)
    if not diff.changed_file_paths:
        raise HTTPException(status_code=400, detail=f"未检测到变更文件（{base}..{head}），请确认项目为 Git 仓库且有提交")

    logger.info("增量审查", project=project.name, files=diff.changed_file_paths,
                added_lines=diff.total_added_lines)

    service = ReviewService(db)
    try:
        review = await service.run_review(
            project=project,
            review_type=review_type,
            trigger_type="incremental",
            file_paths=diff.changed_file_paths,
        )
        return ReviewResponse.model_validate(review)
    except Exception as e:
        logger.error("增量审查失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"增量审查失败: {e}")


@router.post("/run-async", response_model=ReviewResponse, status_code=202)
async def run_review_async(
    project_id: str,
    review_type: str = "full",
    trigger_type: str = "manual",
    db: AsyncSession = Depends(get_db),
):
    """异步执行审查 — 立即返回 running 状态，后台执行

    前端可通过 GET /reviews/{id} 轮询 或 WebSocket /reviews/ws/{id} 接收进度。
    """
    import asyncio

    from app.core.database import async_session_factory

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 创建审查记录（running），立即返回
    from datetime import datetime, timezone
    from app.models.review import Review as ReviewModel

    review = ReviewModel(
        project_id=project.id,
        trigger_type=trigger_type,
        review_type=review_type,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.flush()
    review_id = review.id
    project_id_val = project.id
    review_type_val = review_type
    trigger_type_val = trigger_type

    # 后台执行（独立 DB 会话）
    async def _background():
        async with async_session_factory() as bg_db:
            bg_project_result = await bg_db.execute(select(Project).where(Project.id == project_id_val))
            bg_project = bg_project_result.scalar_one_or_none()
            service = ReviewService(bg_db)
            try:
                await service.run_review(
                    project=bg_project,
                    review_type=review_type_val,
                    trigger_type=trigger_type_val,
                    existing_review_id=review_id,
                )
                await bg_db.commit()
            except Exception as e:
                await bg_db.rollback()
                logger.error("后台审查失败", review_id=review_id, error=str(e))

    asyncio.create_task(_background())

    await db.refresh(review)
    return ReviewResponse.model_validate(review)


@router.websocket("/ws/{review_id}")
async def review_progress_ws(websocket: WebSocket, review_id: str):
    """WebSocket — 推送审查进度事件"""
    await websocket.accept()
    from app.services.progress import progress_emitter

    queue = progress_emitter.subscribe(review_id)
    try:
        # 先推送当前状态
        await websocket.send_json({"event": "connected", "review_id": review_id})
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(msg)
                if msg.get("event") in ("review_completed", "review_failed"):
                    break
            except asyncio.TimeoutError:
                # 心跳保活
                await websocket.send_json({"event": "ping"})
    except WebSocketDisconnect:
        logger.info("WS 客户端断开", review_id=review_id)
    except Exception as e:
        logger.info("WS 异常", review_id=review_id, error=str(e))
    finally:
        progress_emitter.unsubscribe(review_id, queue)


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


@router.get("/{review_id}/report/html")
async def get_review_report_html(
    review_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查看审查报告（HTML 格式）"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="审查不存在")

    project_result = await db.execute(select(Project).where(Project.id == review.project_id))
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown"

    findings_result = await db.execute(
        select(Finding).where(Finding.review_id == review_id).order_by(Finding.severity)
    )
    findings = findings_result.scalars().all()

    generator = ReportGenerator()
    report = generator.generate_html(review, findings, project_name)

    return HTMLResponse(content=report)

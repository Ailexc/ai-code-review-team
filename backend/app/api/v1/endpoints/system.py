"""系统管理 API"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.review import Review
from app.models.finding import Finding
from app.models.llm_usage import LLMUsage
from app.services.metrics import metrics

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
    """系统统计数据（仪表盘用，含历史趋势）"""
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
    acknowledged = (await db.execute(
        select(func.count(Finding.id)).where(Finding.status == "acknowledged")
    )).scalar() or 0

    # 最近审查
    recent = (await db.execute(
        select(Review).order_by(Review.created_at.desc()).limit(10)
    )).scalars().all()

    # 历史趋势 — 按天聚合健康度与发现数量（SQLite/PG 通用）
    trend_rows = (await db.execute(text(
        """
        SELECT
            date(completed_at) AS day,
            ROUND(AVG(health_score_snapshot), 1) AS avg_health,
            SUM(total_findings) AS total_findings,
            SUM(critical_count) AS critical_count,
            SUM(warning_count) AS warning_count
        FROM reviews
        WHERE status = 'completed' AND completed_at IS NOT NULL
        GROUP BY date(completed_at)
        ORDER BY day ASC
        LIMIT 30
        """
    ))).fetchall()

    trends = [
        {
            "date": row[0],
            "health_score": float(row[1] or 0),
            "total_findings": int(row[2] or 0),
            "critical_count": int(row[3] or 0),
            "warning_count": int(row[4] or 0),
        }
        for row in trend_rows
    ]

    # Finding 状态分布
    status_dist = {
        "open": finding_total - fixed - acknowledged,
        "acknowledged": acknowledged,
        "fixed": fixed,
    }

    return {
        "projects_total": project_total,
        "reviews_total": review_total,
        "findings_total": finding_total,
        "findings_critical": critical,
        "findings_warning": warning,
        "findings_suggestion": suggestion,
        "findings_fixed": fixed,
        "findings_acknowledged": acknowledged,
        "findings_status_distribution": status_dist,
        "review_trends": trends,
        "recent_reviews": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "review_type": r.review_type,
                "status": r.status,
                "total_findings": r.total_findings,
                "critical_count": r.critical_count,
                "warning_count": r.warning_count,
                "health_score_snapshot": r.health_score_snapshot,
                "created_at": r.created_at,
            }
            for r in recent
        ],
    }


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """运行时可观测指标 — 从数据库聚合真实数据

    数据源：
    - reviews 表：审查总数、类型/状态分布、平均耗时
    - findings 表：findings 总数、严重度分布、Agent 分布
    - llm_usage 表：LLM 调用次数、token 消耗
    """
    # 审查统计
    review_total = (await db.execute(select(func.count(Review.id)))).scalar() or 0
    review_completed = (await db.execute(
        select(func.count(Review.id)).where(Review.status == "completed")
    )).scalar() or 0
    review_failed = (await db.execute(
        select(func.count(Review.id)).where(Review.status == "failed")
    )).scalar() or 0
    review_running = (await db.execute(
        select(func.count(Review.id)).where(Review.status == "running")
    )).scalar() or 0

    # 审查类型分布
    type_rows = (await db.execute(
        select(Review.review_type, func.count(Review.id))
        .group_by(Review.review_type)
    )).all()
    reviews_by_type = {t: c for t, c in type_rows}

    # 平均耗时（按类型）
    duration_rows = (await db.execute(
        select(Review.review_type, func.avg(Review.duration_seconds))
        .where(Review.duration_seconds.isnot(None))
        .group_by(Review.review_type)
    )).all()
    avg_duration = {t: round(float(d or 0), 1) for t, d in duration_rows}

    # findings 统计
    finding_total = (await db.execute(select(func.count(Finding.id)))).scalar() or 0
    severity_rows = (await db.execute(
        select(Finding.severity, func.count(Finding.id))
        .group_by(Finding.severity)
    )).all()
    findings_by_severity = {s: c for s, c in severity_rows}

    # Agent 分布
    agent_rows = (await db.execute(
        select(Finding.agent_name, func.count(Finding.id))
        .group_by(Finding.agent_name)
    )).all()
    findings_by_agent = {a: c for a, c in agent_rows}

    # LLM 用量（从 llm_usage 表，持久化）
    llm_calls = (await db.execute(select(func.count(LLMUsage.id)))).scalar() or 0
    llm_success = (await db.execute(
        select(func.count(LLMUsage.id)).where(LLMUsage.success == True)
    )).scalar() or 0
    llm_total_tokens = (await db.execute(
        select(func.sum(LLMUsage.total_tokens))
    )).scalar() or 0
    llm_prompt_tokens = (await db.execute(
        select(func.sum(LLMUsage.prompt_tokens))
    )).scalar() or 0
    llm_completion_tokens = (await db.execute(
        select(func.sum(LLMUsage.completion_tokens))
    )).scalar() or 0
    llm_avg_latency = (await db.execute(
        select(func.avg(LLMUsage.latency_ms)).where(LLMUsage.latency_ms.isnot(None))
    )).scalar() or 0

    # LLM 按模型 token 分布
    model_rows = (await db.execute(
        select(LLMUsage.model, func.sum(LLMUsage.total_tokens))
        .group_by(LLMUsage.model)
    )).all()
    tokens_by_model = {m: int(t or 0) for m, t in model_rows}

    return {
        "reviews": {
            "total": review_total,
            "completed": review_completed,
            "failed": review_failed,
            "running": review_running,
            "by_type": reviews_by_type,
            "avg_duration_s": avg_duration,
        },
        "findings": {
            "total": finding_total,
            "by_severity": findings_by_severity,
            "by_agent": findings_by_agent,
        },
        "llm": {
            "calls_total": llm_calls,
            "calls_success": llm_success,
            "calls_failed": llm_calls - llm_success,
            "success_rate": round(llm_success / llm_calls, 3) if llm_calls else 0,
            "total_tokens": int(llm_total_tokens),
            "prompt_tokens": int(llm_prompt_tokens),
            "completion_tokens": int(llm_completion_tokens),
            "avg_latency_ms": round(float(llm_avg_latency or 0), 1),
            "tokens_by_model": tokens_by_model,
        },
    }

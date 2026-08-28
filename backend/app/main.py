"""FastAPI 应用入口"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import init_db
from app.api.v1.router import api_router

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("启动应用", app=settings.APP_NAME, version=settings.APP_VERSION)
    await init_db()
    logger.info("数据库初始化完成")
    # 可观测性：注册 CrewAI 事件桥接器（框架 LLM/工具事件 → review_steps + 全文档案）
    try:
        from app.services.crew_event_bridge import register_crew_event_bridge, shutdown_crew_event_bridge

        register_crew_event_bridge()
        logger.info("CrewAI 事件桥接器已注册")
    except Exception as e:
        logger.warning("CrewAI 事件桥接器注册失败（不影响审查主流程）", error=str(e))
    yield
    try:
        from app.services.crew_event_bridge import shutdown_crew_event_bridge

        await shutdown_crew_event_bridge()
    except Exception:
        pass
    logger.info("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="多Agent协作代码审查系统 API",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "version": settings.APP_VERSION,
    }

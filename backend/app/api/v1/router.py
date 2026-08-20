"""API v1 路由聚合"""

from fastapi import APIRouter

from app.api.v1.endpoints import projects, reviews, findings, system, triggers, llm_configs

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(projects.router, prefix="/projects", tags=["项目管理"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["审查管理"])
api_router.include_router(findings.router, prefix="/findings", tags=["发现管理"])
api_router.include_router(system.router, prefix="/system", tags=["系统管理"])
api_router.include_router(triggers.router, prefix="/triggers", tags=["触发器"])
api_router.include_router(llm_configs.router, prefix="/llm-configs", tags=["模型配置"])

"""pytest 全局配置 — 使用独立的测试数据库，避免污染开发数据"""

import asyncio
import os
from pathlib import Path

# 必须在导入 app 之前设置测试数据库
_TEST_DB = Path(__file__).resolve().parent.parent / "data" / "test_code_review.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"
os.environ["DEBUG"] = "False"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import init_db, async_session_factory
from app.services.metrics import metrics
from sqlalchemy import text


@pytest_asyncio.fixture
async def client():
    """提供测试用 HTTP 客户端（每个用例独立事务隔离数据库）"""
    await init_db()
    # 重置全局指标，避免测试间数据累积
    metrics.reset()
    # 清空数据，保证用例隔离
    async with async_session_factory() as db:
        for table in ("findings", "reviews", "llm_configs", "projects"):
            await db.execute(text(f"DELETE FROM {table}"))
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

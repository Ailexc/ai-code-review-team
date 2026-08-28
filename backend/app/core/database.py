"""数据库配置"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 创建异步引擎
# SQLite 优化：connect_args.timeout 设置 busy timeout（等待锁释放而非立即报错），
# 配合连接时 PRAGMA（WAL 模式）大幅缓解并发读写时的 "database is locked" 问题。
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args={"timeout": 30},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """连接时启用 SQLite WAL 模式 + busy timeout，减少并发写锁冲突"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入用）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表 + 轻量列迁移）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)


# 轻量列迁移：create_all 只建缺失的表，不会给已有表加列。
# 这里按 (表, 列, DDL) 声明新增列，PRAGMA 检查缺列才执行 ALTER（幂等）。
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("reviews", "orchestration_mode",
     "ALTER TABLE reviews ADD COLUMN orchestration_mode VARCHAR(20) NOT NULL DEFAULT 'parallel'"),
]


async def _ensure_columns(conn) -> None:
    """幂等补齐已存在表缺失的列（SQLite ALTER ADD COLUMN 支持带默认值）"""
    from sqlalchemy import text

    for table, column, ddl in _PENDING_COLUMNS:
        try:
            rows = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in rows.fetchall()}
            if column not in existing:
                await conn.execute(text(ddl))
        except Exception as e:
            # 迁移失败不阻断启动（新库由 create_all 直接建出全列，无需 ALTER）
            import structlog
            structlog.get_logger().warning("列迁移跳过", table=table, column=column, error=str(e))

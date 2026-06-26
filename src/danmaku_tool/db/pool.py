"""SQLite 连接管理。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from ..config import settings

logger = logging.getLogger(__name__)

_db_path: Path | None = None


def _get_db_path() -> Path:
    """获取数据库路径。"""
    global _db_path
    if _db_path is None:
        _db_path = settings.db_path
        _db_path.parent.mkdir(parents=True, exist_ok=True)
    return _db_path


async def init_db() -> None:
    """初始化数据库：执行建表迁移。"""
    db_path = _get_db_path()
    logger.info(f"数据库路径: {db_path}")

    migrations_dir = Path(__file__).parent / "migrations"

    async with aiosqlite.connect(str(db_path)) as conn:
        # 001: 建表
        sql = (migrations_dir / "001_init.sql").read_text(encoding="utf-8")
        await conn.executescript(sql)

        # 002: 添加 duration_limit 列（幂等）
        try:
            await conn.execute("ALTER TABLE tasks ADD COLUMN duration_limit REAL")
        except aiosqlite.OperationalError:
            pass  # 列已存在

        await conn.commit()

    logger.info("数据库初始化完成")


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """获取数据库连接（异步上下文管理器）。"""
    db_path = _get_db_path()
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()

"""FastAPI 依赖注入。"""
from __future__ import annotations

from collections.abc import AsyncIterator

import aiosqlite

from .db.pool import get_db
from .queue.task_queue import TaskQueue

# 全局任务队列实例（在 main.py lifespan 中初始化）
_queue: TaskQueue | None = None


def set_queue(queue: TaskQueue) -> None:
    """设置全局任务队列。"""
    global _queue
    _queue = queue


def get_queue() -> TaskQueue:
    """获取全局任务队列。"""
    if _queue is None:
        raise RuntimeError("TaskQueue 未初始化")
    return _queue


async def get_db_conn() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI 依赖：获取数据库连接。"""
    async with get_db() as conn:
        yield conn

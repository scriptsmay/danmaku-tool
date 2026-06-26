"""Task 数据访问层。"""
from __future__ import annotations

import json

import aiosqlite

from ..models.task import Task, TaskStatus, TaskType


def _row_to_task(row: aiosqlite.Row) -> Task:
    """将数据库行转换为 Task 对象。"""
    return Task(
        id=row["id"],
        type=TaskType(row["type"]),
        status=TaskStatus(row["status"]),
        video_path=row["video_path"],
        ass_path=row["ass_path"],
        jsonl_path=row["jsonl_path"],
        output_path=row["output_path"],
        encoder=row["encoder"] or "auto",
        fps=row["fps"] or 30,
        offset_ms=row["offset_ms"] or 0,
        video_width=row["video_width"],
        video_height=row["video_height"],
        duration_limit=row["duration_limit"],
        callback_url=row["callback_url"],
        metadata=row["metadata"],
        progress=row["progress"] or 0.0,
        speed=row["speed"],
        output_size=row["output_size"],
        error=row["error"],
        created_at=row["created_at"] or "",
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


async def insert(conn: aiosqlite.Connection, task: Task) -> None:
    """插入任务。"""
    await conn.execute(
        """INSERT INTO tasks
           (id, type, status, video_path, ass_path, jsonl_path, output_path,
            encoder, fps, offset_ms, video_width, video_height, duration_limit,
            callback_url, metadata, progress, speed, output_size, error,
            created_at, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task.id, task.type.value, task.status.value,
            task.video_path, task.ass_path, task.jsonl_path, task.output_path,
            task.encoder, task.fps, task.offset_ms, task.video_width, task.video_height,
            task.duration_limit,
            task.callback_url, task.metadata,
            task.progress, task.speed, task.output_size, task.error,
            task.created_at, task.started_at, task.completed_at,
        ),
    )
    await conn.commit()


async def update(conn: aiosqlite.Connection, task: Task) -> None:
    """更新任务。"""
    await conn.execute(
        """UPDATE tasks SET
           status=?, progress=?, speed=?, output_size=?, error=?,
           started_at=?, completed_at=?, output_path=?
           WHERE id=?""",
        (
            task.status.value, task.progress, task.speed, task.output_size,
            task.error, task.started_at, task.completed_at, task.output_path,
            task.id,
        ),
    )
    await conn.commit()


async def get(conn: aiosqlite.Connection, task_id: str) -> Task | None:
    """获取单个任务。"""
    cursor = await conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    row = await cursor.fetchone()
    return _row_to_task(row) if row else None


async def list_all(
    conn: aiosqlite.Connection, limit: int = 50, offset: int = 0
) -> list[Task]:
    """列出任务（按创建时间倒序）。"""
    cursor = await conn.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [_row_to_task(r) for r in rows]


async def delete(conn: aiosqlite.Connection, task_id: str) -> bool:
    """删除任务。"""
    cursor = await conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    await conn.commit()
    return cursor.rowcount > 0


async def list_unfinished(conn: aiosqlite.Connection) -> list[Task]:
    """查询未完成的任务（queued + processing）。"""
    cursor = await conn.execute(
        "SELECT * FROM tasks WHERE status IN ('queued', 'processing') ORDER BY created_at ASC"
    )
    rows = await cursor.fetchall()
    return [_row_to_task(r) for r in rows]

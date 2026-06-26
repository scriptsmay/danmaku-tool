"""任务查询 + SSE 进度推送。"""
from __future__ import annotations

import asyncio
import json
import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..db import tasks_dao
from ..deps import get_db_conn, get_queue
from ..models.task import TaskStatus
from ..queue.task_queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


class TaskResponse(BaseModel):
    """任务详情响应。"""
    id: str
    type: str
    status: str
    video_path: str | None
    ass_path: str | None
    jsonl_path: str | None
    output_path: str | None
    encoder: str
    fps: int
    offset_ms: int
    progress: float
    speed: str | None
    output_size: int | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class TaskListResponse(BaseModel):
    """任务列表响应。"""
    tasks: list[TaskResponse]
    total: int


def _task_to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        type=task.type.value,
        status=task.status.value,
        video_path=task.video_path,
        ass_path=task.ass_path,
        jsonl_path=task.jsonl_path,
        output_path=task.output_path,
        encoder=task.encoder,
        fps=task.fps,
        offset_ms=task.offset_ms,
        progress=task.progress,
        speed=task.speed,
        output_size=task.output_size,
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
    limit: int = 50,
    offset: int = 0,
    queue: TaskQueue = Depends(get_queue),
) -> TaskListResponse:
    """查询任务列表（内存队列 + 数据库历史）。"""
    from ..db import tasks_dao
    from ..db.pool import get_db

    # 内存中的任务（含活跃任务）
    memory_tasks = {t.id: t for t in queue.get_all_tasks()}

    # 数据库中的历史任务
    async with get_db() as db:
        db_tasks = await tasks_dao.list_all(db, limit=200, offset=0)

    # 合并：内存优先（更实时），补充数据库中没有的
    merged = dict(memory_tasks)
    for t in db_tasks:
        if t.id not in merged:
            merged[t.id] = t

    all_tasks = sorted(merged.values(), key=lambda t: t.created_at, reverse=True)
    total = len(all_tasks)
    page = all_tasks[offset:offset + limit]
    return TaskListResponse(
        tasks=[_task_to_response(t) for t in page],
        total=total,
    )


@router.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
) -> TaskResponse:
    """查询单个任务状态。"""
    task = queue.get_task(task_id)
    if not task:
        from ..db import tasks_dao
        from ..db.pool import get_db
        async with get_db() as db:
            task = await tasks_dao.get(db, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return _task_to_response(task)


@router.post("/api/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
):
    """重试任务：失败→原地重入队；已完成→复制新任务入队。"""
    new_task = await queue.retry(task_id)
    if not new_task:
        # 内存中没有（旧进程创建的），从 DB 加载后复制
        from ..db import tasks_dao
        from ..db.pool import get_db
        async with get_db() as db:
            old_task = await tasks_dao.get(db, task_id)
        if not old_task or old_task.status.value not in ("completed", "failed"):
            raise HTTPException(400, "任务不存在或状态不可重试")
        new_task = Task(
            type=old_task.type,
            video_path=old_task.video_path,
            ass_path=old_task.ass_path,
            jsonl_path=old_task.jsonl_path,
            encoder=old_task.encoder,
            fps=old_task.fps,
            offset_ms=old_task.offset_ms,
            video_width=old_task.video_width,
            video_height=old_task.video_height,
            duration_limit=old_task.duration_limit,
            callback_url=old_task.callback_url,
            metadata=old_task.metadata,
        )
        new_task.created_at = datetime.now().isoformat()
        async with get_db() as db:
            await tasks_dao.insert(db, new_task)
        await queue.put(new_task)
    return {"ok": True, "new_task_id": new_task.id}


@router.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
):
    """删除任务记录。"""
    from ..db.pool import get_db

    queue.remove(task_id)
    async with get_db() as db:
        from ..db import tasks_dao
        await tasks_dao.delete(db, task_id)
    return {"ok": True}


@router.get("/api/tasks/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
):
    """SSE 实时推送任务进度。"""
    async def event_generator():
        while True:
            task = queue.get_task(task_id)
            if task is None:
                yield {"event": "error", "data": json.dumps({"error": "任务不存在"})}
                break

            yield {
                "event": "progress",
                "data": json.dumps({
                    "status": task.status.value,
                    "progress": task.progress,
                    "speed": task.speed or "",
                }),
            }

            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "status": task.status.value,
                        "output_path": task.output_path or "",
                        "output_size": task.output_size or 0,
                        "error": task.error or "",
                    }),
                }
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())

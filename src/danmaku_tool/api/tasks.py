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
    """查询任务列表。"""
    all_tasks = queue.get_all_tasks()
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
        raise HTTPException(404, "任务不存在")
    return _task_to_response(task)


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

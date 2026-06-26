"""基于 asyncio 的内存任务队列。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Coroutine, Optional, Any

from ..models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """内存任务队列，带并发控制。"""

    def __init__(self, max_concurrent: int = 1):
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._tasks: dict[str, Task] = {}  # task_id -> Task（所有任务，含已完成）
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def put(self, task: Task) -> None:
        """入队。"""
        self._tasks[task.id] = task
        await self._queue.put(task)
        logger.info(f"任务入队: {task.id} (type={task.type.value})")

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务（任何状态）。"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        """获取所有任务（按创建时间倒序）。"""
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    async def cancel(self, task_id: str) -> bool:
        """取消排队中的任务。"""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.QUEUED:
            task.status = TaskStatus.CANCELLED
            logger.info(f"任务已取消: {task_id}")
            return True
        return False

    async def retry(self, task_id: str) -> Optional[Task]:
        """重试任务：失败→原地重入队；已完成→复制新任务入队。返回新入队的 Task。"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if task.status == TaskStatus.FAILED:
            task.status = TaskStatus.QUEUED
            task.progress = 0.0
            task.speed = None
            task.error = None
            task.started_at = None
            task.completed_at = None
            await self._queue.put(task)
            logger.info(f"任务重试(原地): {task_id}")
            return task

        if task.status == TaskStatus.COMPLETED:
            new_task = Task(
                type=task.type,
                video_path=task.video_path,
                ass_path=task.ass_path,
                jsonl_path=task.jsonl_path,
                encoder=task.encoder,
                fps=task.fps,
                offset_ms=task.offset_ms,
                video_width=task.video_width,
                video_height=task.video_height,
                duration_limit=task.duration_limit,
                callback_url=task.callback_url,
                metadata=task.metadata,
            )
            new_task.created_at = datetime.now().isoformat()
            await self.put(new_task)
            logger.info(f"任务重试(复制): {task_id} → {new_task.id}")
            return new_task

        return None

    def remove(self, task_id: str) -> bool:
        """从内存队列移除任务。"""
        task = self._tasks.pop(task_id, None)
        if task:
            logger.info(f"任务已从内存移除: {task_id}")
            return True
        return False

    async def restore(self, tasks: list[Task]) -> None:
        """从数据库恢复未完成任务并重新入队。"""
        for task in tasks:
            self._tasks[task.id] = task
            if task.status == TaskStatus.PROCESSING:
                task.status = TaskStatus.QUEUED
                task.progress = 0.0
                task.speed = None
            await self._queue.put(task)
            logger.info(f"恢复任务: {task.id} (type={task.type.value})")
        if tasks:
            logger.info(f"共恢复 {len(tasks)} 个未完成任务")

    @property
    def queue_depth(self) -> int:
        """队列中等待的任务数。"""
        return self._queue.qsize()

    @property
    def processing_count(self) -> int:
        """正在处理的任务数。"""
        return sum(1 for t in self._tasks.values() if t.status == TaskStatus.PROCESSING)

    async def start_worker(
        self, handler: Callable[[Task], Coroutine[Any, Any, None]]
    ) -> None:
        """启动 worker 循环。"""
        self._running = True
        logger.info("Worker 已启动")
        while self._running:
            task = await self._queue.get()
            if task.status == TaskStatus.CANCELLED:
                continue
            async with self._semaphore:
                await handler(task)

    def stop(self) -> None:
        """停止 worker。"""
        self._running = False
        logger.info("Worker 已停止")

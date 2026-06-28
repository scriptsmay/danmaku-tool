"""任务队列测试。"""
from __future__ import annotations

import asyncio

import pytest

from danmaku_tool.models.task import Task, TaskStatus, TaskType
from danmaku_tool.queue.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_put_and_get():
    queue = TaskQueue(max_concurrent=1)
    task = Task(type=TaskType.BURN)
    await queue.put(task)

    assert queue.get_task(task.id) is task
    assert queue.queue_depth == 1


@pytest.mark.asyncio
async def test_get_all_tasks():
    queue = TaskQueue(max_concurrent=1)
    t1 = Task(type=TaskType.BURN)
    t2 = Task(type=TaskType.ASS_GENERATE)
    await queue.put(t1)
    await queue.put(t2)

    all_tasks = queue.get_all_tasks()
    assert len(all_tasks) == 2


@pytest.mark.asyncio
async def test_cancel_queued():
    queue = TaskQueue(max_concurrent=1)
    task = Task(type=TaskType.BURN)
    await queue.put(task)

    result = await queue.cancel(task.id)
    assert result is True
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_processing_fails():
    queue = TaskQueue(max_concurrent=1)
    task = Task(type=TaskType.BURN, status=TaskStatus.PROCESSING)
    await queue.put(task)

    result = await queue.cancel(task.id)
    assert result is False


@pytest.mark.asyncio
async def test_worker_processes_task():
    queue = TaskQueue(max_concurrent=1)
    processed = []

    async def handler(task: Task):
        processed.append(task.id)
        task.status = TaskStatus.COMPLETED

    task = Task(type=TaskType.BURN)
    await queue.put(task)

    # 启动 worker 并等待处理
    worker = asyncio.create_task(queue.start_worker(handler))
    await asyncio.sleep(0.2)
    queue.stop()
    await asyncio.sleep(0.1)

    assert task.id in processed
    assert task.status == TaskStatus.COMPLETED
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_processing_count():
    queue = TaskQueue(max_concurrent=1)
    t1 = Task(type=TaskType.BURN, status=TaskStatus.PROCESSING)
    t2 = Task(type=TaskType.BURN, status=TaskStatus.QUEUED)
    await queue.put(t1)
    await queue.put(t2)

    assert queue.processing_count == 1


@pytest.mark.asyncio
async def test_retry_completed_copies_output_path_and_created_at():
    queue = TaskQueue(max_concurrent=1)
    task = Task(
        type=TaskType.BURN,
        status=TaskStatus.COMPLETED,
        video_path="input.ts",
        ass_path="input.ass",
        output_path="output.mp4",
    )
    await queue.put(task)

    new_task = await queue.retry(task.id)

    assert new_task is not None
    assert new_task.id != task.id
    assert new_task.output_path == "output.mp4"
    assert new_task.created_at

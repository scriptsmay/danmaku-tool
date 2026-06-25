"""任务查询 API 测试。"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from danmaku_tool.main import app
from danmaku_tool.deps import set_queue
from danmaku_tool.queue.task_queue import TaskQueue
from danmaku_tool.models.task import Task, TaskType, TaskStatus


@pytest.fixture(autouse=True)
def setup_queue():
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)
    yield


@pytest.mark.asyncio
async def test_list_tasks_with_data():
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)

    t1 = Task(type=TaskType.BURN, status=TaskStatus.COMPLETED)
    t2 = Task(type=TaskType.ASS_GENERATE, status=TaskStatus.QUEUED)
    await queue.put(t1)
    await queue.put(t2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["tasks"]) == 2


@pytest.mark.asyncio
async def test_get_task_by_id():
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)

    task = Task(type=TaskType.BURN, status=TaskStatus.PROCESSING, progress=42.5)
    await queue.put(task)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{task.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task.id
        assert data["status"] == "processing"
        assert data["progress"] == 42.5


@pytest.mark.asyncio
async def test_delete_task(sample_video, sample_ass):
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)

    task = Task(type=TaskType.BURN, status=TaskStatus.COMPLETED)
    await queue.put(task)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 先通过 API 创建任务来写入 DB
        resp = await client.post("/api/burn", json={
            "video_path": str(sample_video),
            "ass_path": str(sample_ass),
        })
        task_id = resp.json()["task_id"]

        # 删除
        resp = await client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # 再次删除应 404
        resp = await client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 404

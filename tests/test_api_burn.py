"""压制 API 测试。"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from danmaku_tool.main import app
from danmaku_tool.deps import set_queue
from danmaku_tool.queue.task_queue import TaskQueue


@pytest.fixture(autouse=True)
def setup_queue():
    """每个测试前重置队列。"""
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)
    yield


@pytest.mark.asyncio
async def test_create_burn_task(sample_video, sample_ass):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/burn", json={
            "video_path": str(sample_video),
            "ass_path": str(sample_ass),
            "encoder": "cpu",
            "fps": 30,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_create_burn_task_missing_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/burn", json={
            "video_path": "/nonexistent/video.mp4",
            "ass_path": "/nonexistent/ass.ass",
        })
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_burn_task_invalid_ext(tmp_path):
    fake = tmp_path / "test.txt"
    fake.write_text("x")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/burn", json={
            "video_path": str(fake),
            "ass_path": str(fake),
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["tasks"] == []


@pytest.mark.asyncio
async def test_get_task_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/tasks/nonexistent_id")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_task_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/tasks/nonexistent_id/cancel")
        assert resp.status_code == 400

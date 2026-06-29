"""压制 API 测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from danmaku_tool.config import settings
from danmaku_tool.deps import get_queue, set_queue
from danmaku_tool.main import app
from danmaku_tool.models.task import Task
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
        task = get_queue().get_task(data["task_id"])
        assert task is not None
        assert task.created_at


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


@pytest.mark.asyncio
async def test_create_session_burn_tasks(tmp_path, monkeypatch, sample_jsonl):
    session_root = tmp_path / "sessions"
    session_dir = session_root / "42"
    danmaku_dir = session_dir / "danmaku"
    output_dir = tmp_path / "output"
    danmaku_dir.mkdir(parents=True)
    output_dir.mkdir()

    (session_dir / "20260627_220247.ts").write_bytes(b"video1")
    (session_dir / "20260627_230241.ts").write_bytes(b"video2")
    (danmaku_dir / "danmaku.jsonl").write_text(sample_jsonl.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(settings, "session_dir", session_root)
    monkeypatch.setattr(settings, "danmaku_output_dir", output_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/burn/session", json={"session_id": "42"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["video_count"] == 2
    assert len(data["task_ids"]) == 2

    queue = get_queue()
    for task_id in data["task_ids"]:
        task = queue.get_task(task_id)
        assert task is not None
        assert task.jsonl_path == str(danmaku_dir / "danmaku.jsonl")
        assert task.ass_path is not None
        assert Path(task.ass_path).exists()
        assert task.output_path
        assert task.created_at


@pytest.mark.asyncio
async def test_create_session_burn_avoids_active_output_collision(tmp_path, monkeypatch, sample_jsonl):
    session_root = tmp_path / "sessions"
    session_dir = session_root / "42"
    danmaku_dir = session_dir / "danmaku"
    output_dir = tmp_path / "output"
    danmaku_dir.mkdir(parents=True)
    output_dir.mkdir()

    video = session_dir / "20260627_220247.ts"
    video.write_bytes(b"video")
    (danmaku_dir / "danmaku.jsonl").write_text(sample_jsonl.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(settings, "session_dir", session_root)
    monkeypatch.setattr(settings, "danmaku_output_dir", output_dir)

    base_output = output_dir / "20260627_220247_danmaku.mp4"
    queue = get_queue()
    await queue.put(Task(output_path=str(base_output)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/burn/session", json={"session_id": "42"})

    assert resp.status_code == 200
    task = queue.get_task(resp.json()["task_ids"][0])
    assert task is not None
    assert task.output_path != str(base_output)
    assert task.output_path.startswith(str(output_dir / "20260627_220247_danmaku_"))

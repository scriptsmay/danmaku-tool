"""文件浏览器 API 测试。"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from danmaku_tool.deps import set_queue
from danmaku_tool.main import app
from danmaku_tool.queue.task_queue import TaskQueue


@pytest.fixture(autouse=True)
def setup_queue():
    queue = TaskQueue(max_concurrent=1)
    set_queue(queue)
    yield


@pytest.mark.asyncio
async def test_browse_root():
    """浏览根目录应返回 allowed_roots。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/files/browse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == ""
        assert data["parent"] is None
        assert isinstance(data["entries"], list)


@pytest.mark.asyncio
async def test_browse_path_traversal():
    """路径穿越应被拒绝。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/files/browse?path=../../etc")
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_browse_not_allowed():
    """不在白名单中的目录应被拒绝。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/files/browse?path=/tmp")
        assert resp.status_code == 403

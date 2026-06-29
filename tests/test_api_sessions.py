"""会话列表 API 测试。"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from danmaku_tool.config import settings
from danmaku_tool.main import app
from danmaku_tool.utils import VIDEO_EXTS, parse_ts_from_filename

# ── utils 工具函数测试 ──


def test_parse_ts_from_filename_valid():
    ts = parse_ts_from_filename("20260625_215745.ts")
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 6
    assert ts.day == 25
    assert ts.hour == 21
    assert ts.minute == 57
    assert ts.second == 45


def test_parse_ts_from_filename_dash_separator():
    ts = parse_ts_from_filename("20260625-215745.mp4")
    assert ts is not None
    assert ts.hour == 21


def test_parse_ts_from_filename_no_timestamp():
    assert parse_ts_from_filename("video.mp4") is None


def test_parse_ts_from_filename_invalid_date():
    assert parse_ts_from_filename("99991332_256199.ts") is None


def test_video_exts():
    assert ".ts" in VIDEO_EXTS
    assert ".mp4" in VIDEO_EXTS
    assert ".mkv" in VIDEO_EXTS
    assert ".flv" in VIDEO_EXTS
    assert ".avi" not in VIDEO_EXTS


# ── GET /api/sessions ──


@pytest.mark.asyncio
async def test_list_sessions_no_config(monkeypatch):
    """session_dir 未配置时返回 404。"""
    monkeypatch.setattr(settings, "session_dir", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_dir_not_exists(tmp_path, monkeypatch):
    """会话目录不存在时返回 404。"""
    monkeypatch.setattr(settings, "session_dir", tmp_path / "nonexistent")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_empty(tmp_path, monkeypatch):
    """空会话目录返回空列表。"""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(settings, "session_dir", session_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []
        assert data["session_dir"] == str(session_dir)


@pytest.mark.asyncio
async def test_list_sessions_with_video(tmp_path, monkeypatch):
    """有视频文件的会话应出现在列表中。"""
    session_dir = tmp_path / "sessions"
    session = session_dir / "42"
    danmaku_dir = session / "danmaku"
    danmaku_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "session_dir", session_dir)

    video = session / "20260627_220247.ts"
    video.write_bytes(b"\x00" * 2048)
    (danmaku_dir / "danmaku.jsonl").write_text(
        '{"ts_ms":1000,"type":"comment","text":"test","username":"u"}', encoding="utf-8"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1

        s = data["sessions"][0]
        assert s["session_id"] == "42"
        assert s["video_count"] == 1
        assert s["has_danmaku"] is True
        assert s["total_size"] == 2048
        assert s["created_at"]

        # segments 字段验证
        assert len(s["segments"]) == 1
        seg = s["segments"][0]
        assert seg["name"] == "20260627_220247.ts"
        assert seg["size"] == 2048
        assert seg["start_time"] is not None  # 文件名有时间戳


@pytest.mark.asyncio
async def test_list_sessions_no_danmaku(tmp_path, monkeypatch):
    """无弹幕文件时会话仍应列出，has_danmaku 为 false。"""
    session_dir = tmp_path / "sessions"
    session = session_dir / "99"
    session.mkdir(parents=True)
    monkeypatch.setattr(settings, "session_dir", session_dir)

    (session / "video.mp4").write_bytes(b"\x00" * 512)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["has_danmaku"] is False


@pytest.mark.asyncio
async def test_list_sessions_skips_no_video_dirs(tmp_path, monkeypatch):
    """没有视频文件的子目录不应出现在会话列表中。"""
    session_dir = tmp_path / "sessions"
    empty_sub = session_dir / "empty_session"
    empty_sub.mkdir(parents=True)
    (empty_sub / "readme.txt").write_text("not a video")
    monkeypatch.setattr(settings, "session_dir", session_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 0


@pytest.mark.asyncio
async def test_list_sessions_multiple_videos(tmp_path, monkeypatch):
    """多视频会话应返回正确的 segment 列表和时间信息。"""
    session_dir = tmp_path / "sessions"
    session = session_dir / "28"
    danmaku_dir = session / "danmaku"
    danmaku_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "session_dir", session_dir)

    (session / "20260628_200000.ts").write_bytes(b"\x00" * 1000)
    (session / "20260628_210000.ts").write_bytes(b"\x00" * 2000)
    (session / "20260628_220000.ts").write_bytes(b"\x00" * 3000)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1

        s = data["sessions"][0]
        assert s["video_count"] == 3
        assert s["total_size"] == 6000
        assert len(s["segments"]) == 3
        assert len(s["video_files"]) == 3

        # 按文件名排序，检查 start_time
        for seg in s["segments"]:
            assert seg["start_time"] is not None

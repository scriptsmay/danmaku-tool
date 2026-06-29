"""会话列表 API — 扫描 session_dir 下的所有会话。"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..utils import VIDEO_EXTS, parse_ts_from_filename

logger = logging.getLogger(__name__)
router = APIRouter()


class SegmentFileInfo(BaseModel):
    """分段视频文件信息。"""
    name: str
    size: int
    start_time: str | None = None  # 从文件名解析的录制开始时间


class SessionItem(BaseModel):
    """单个会话信息。"""
    session_id: str
    video_count: int
    video_files: list[str]
    segments: list[SegmentFileInfo]
    has_danmaku: bool
    total_size: int
    created_at: str


class SessionListResponse(BaseModel):
    """会话列表响应。"""
    session_dir: str
    sessions: list[SessionItem]


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    """列出 session_dir 下所有会话目录。"""
    if not settings.session_dir:
        raise HTTPException(404, "DANMAKU_SESSION_DIR 未配置")

    session_dir = settings.session_dir
    if not session_dir.is_dir():
        raise HTTPException(404, f"会话目录不存在: {session_dir}")

    sessions: list[SessionItem] = []

    for entry in session_dir.iterdir():
        if not entry.is_dir():
            continue

        videos = sorted(
            p for p in entry.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        )
        if not videos:
            continue

        jsonl_path = entry / "danmaku" / "danmaku.jsonl"
        total_size = 0
        segments: list[SegmentFileInfo] = []
        for v in videos:
            try:
                size = v.stat().st_size
            except OSError:
                size = 0
            total_size += size
            ts = parse_ts_from_filename(v.name)
            segments.append(SegmentFileInfo(
                name=v.name,
                size=size,
                start_time=ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None,
            ))

        try:
            created_at = datetime.fromtimestamp(
                entry.stat().st_ctime, tz=UTC
            ).isoformat()
        except OSError:
            created_at = ""

        sessions.append(SessionItem(
            session_id=entry.name,
            video_count=len(videos),
            video_files=[p.name for p in videos],
            segments=segments,
            has_danmaku=jsonl_path.exists(),
            total_size=total_size,
            created_at=created_at,
        ))

    # 按创建时间倒序
    sessions.sort(key=lambda s: s.created_at, reverse=True)

    return SessionListResponse(
        session_dir=str(session_dir),
        sessions=sessions,
    )

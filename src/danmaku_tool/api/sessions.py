"""会话列表 API — 扫描 session_dir 下的所有会话。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

VIDEO_EXTS = {".ts", ".mp4", ".mkv", ".flv"}


class SessionItem(BaseModel):
    """单个会话信息。"""
    session_id: str
    video_count: int
    video_files: list[str]
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
        total_size = sum(p.stat().st_size for p in videos)

        try:
            created_at = datetime.fromtimestamp(
                entry.stat().st_ctime, tz=timezone.utc
            ).isoformat()
        except OSError:
            created_at = ""

        sessions.append(SessionItem(
            session_id=entry.name,
            video_count=len(videos),
            video_files=[p.name for p in videos],
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

"""ASS 生成 API。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..core.ass_generator import DanmakuAssGenerator, SegmentInfo
from ..db import tasks_dao
from ..deps import get_db_conn, get_queue
from ..models.task import Task, TaskType
from ..queue.task_queue import TaskQueue
from ..utils import VIDEO_EXTS, parse_ts_from_filename

logger = logging.getLogger(__name__)
router = APIRouter()


async def _ffprobe_duration(ffprobe_path: str, video_path: str) -> float:
    """用 ffprobe 获取视频时长（秒）。"""
    proc = await asyncio.create_subprocess_exec(
        ffprobe_path,
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except ValueError:
        logger.warning("ffprobe 无法获取视频时长: %s, stderr=%s", video_path, stderr.decode(errors="replace")[:200])
        return 0.0


def _count_jsonl_lines_sync(path: Path) -> int:
    """同步统计 JSONL 文件行数。"""
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


async def _count_jsonl_lines(path: Path) -> int:
    """异步统计 JSONL 文件行数（在线程中执行以避免阻塞事件循环）。"""
    return await asyncio.to_thread(_count_jsonl_lines_sync, path)


class SegmentParam(BaseModel):
    """分段参数。"""
    recording_file_id: int
    start_ms: int
    end_ms: int
    output_path: str


class AssGenerateRequest(BaseModel):
    """ASS 生成请求。"""
    jsonl_path: str = Field(..., description="JSONL 弹幕文件路径")
    output_path: str = Field(..., description="输出 ASS 文件路径")
    video_width: int = Field(1920, description="视频宽度")
    video_height: int = Field(1080, description="视频高度")
    offset_ms: int = Field(0, description="时间偏移（ms）")
    segments: list[SegmentParam] | None = Field(None, description="分段参数")
    callback_url: str | None = Field(None)

    @field_validator("jsonl_path")
    @classmethod
    def validate_jsonl_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"文件不存在: {v}")
        return v


class AssGenerateResponse(BaseModel):
    """ASS 生成响应。"""
    task_id: str
    status: str
    message: str


@router.post("/api/ass/generate", response_model=AssGenerateResponse)
async def generate_ass(
    req: AssGenerateRequest,
    queue: TaskQueue = Depends(get_queue),
    db: aiosqlite.Connection = Depends(get_db_conn),
) -> AssGenerateResponse:
    """生成 ASS 字幕。"""
    task = Task(
        type=TaskType.ASS_GENERATE,
        jsonl_path=req.jsonl_path,
        output_path=req.output_path,
        video_width=req.video_width,
        video_height=req.video_height,
        callback_url=req.callback_url,
    )

    await tasks_dao.insert(db, task)
    await queue.put(task)

    logger.info(f"创建 ASS 生成任务: {task.id}")
    return AssGenerateResponse(task_id=task.id, status="queued", message="ASS 生成任务已加入队列")


@router.post("/api/ass/generate-sync")
async def generate_ass_sync(req: AssGenerateRequest) -> dict:
    """同步生成 ASS 字幕（不经过队列，直接执行）。"""
    generator = DanmakuAssGenerator(
        font_family=settings.font_family,
        font_size=settings.font_size,
        opacity=settings.opacity,
        outline_width=settings.outline_width,
        max_per_second=settings.max_per_second,
    )

    if req.segments:
        from ..core.ass_generator import SegmentInfo
        segments = [
            SegmentInfo(
                recording_file_id=s.recording_file_id,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                output_path=s.output_path,
            )
            for s in req.segments
        ]
        generated = await generator.generate_segment_ass(
            jsonl_path=req.jsonl_path,
            output_dir=str(Path(req.output_path).parent),
            segments=segments,
            video_width=req.video_width,
            video_height=req.video_height,
        )
        return {"status": "completed", "generated_files": generated}
    else:
        ass_path = await generator.generate_from_jsonl(
            jsonl_path=req.jsonl_path,
            ass_path=req.output_path,
            video_width=req.video_width,
            video_height=req.video_height,
            offset_ms=req.offset_ms,
        )
        return {"status": "completed", "output_path": ass_path}


class SessionAssRequest(BaseModel):
    """会话级 ASS 生成请求。"""
    session_id: str = Field(..., description="录制会话 ID")
    video_width: int = Field(1920, description="视频宽度")
    video_height: int = Field(1080, description="视频高度")


@router.post("/api/ass/generate-session")
async def generate_session_ass(req: SessionAssRequest) -> dict:
    """为会话中的每个视频分段生成同名 ASS 字幕（同步，不经过队列）。

    通过文件名时间戳 + ffprobe 时长计算每段的弹幕时间窗口，
    ASS 文件输出到视频同级目录，文件名与视频相同（扩展名 .ass）。
    """
    if not settings.session_dir:
        raise HTTPException(404, "DANMAKU_SESSION_DIR 未配置")

    session_path = settings.session_dir / req.session_id
    if not session_path.is_dir():
        raise HTTPException(404, f"会话目录不存在: {session_path}")

    jsonl_path = session_path / "danmaku" / "danmaku.jsonl"
    if not jsonl_path.exists():
        raise HTTPException(404, f"弹幕文件不存在: {jsonl_path}")

    # 扫描视频文件
    videos = sorted(
        p for p in session_path.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    if not videos:
        raise HTTPException(404, f"未找到视频文件: {session_path}")

    # 解析每个视频的时间戳
    video_ts_map: dict[Path, datetime | None] = {}
    for v in videos:
        video_ts_map[v] = parse_ts_from_filename(v.name)

    has_ts = all(ts is not None for ts in video_ts_map.values())

    generator = DanmakuAssGenerator(
        font_family=settings.font_family,
        font_size=settings.font_size,
        opacity=settings.opacity,
        outline_width=settings.outline_width,
        max_per_second=settings.max_per_second,
    )

    generated: list[str] = []

    if has_ts and len(videos) > 1:
        # 多分段模式：按文件名时间戳 + ffprobe 时长计算弹幕时间窗口
        earliest_ts = min(ts for ts in video_ts_map.values() if ts is not None)

        # 并发获取所有视频时长
        durations = await asyncio.gather(
            *[_ffprobe_duration(settings.ffprobe_path, str(v)) for v in videos]
        )

        segments: list[SegmentInfo] = []
        for i, video in enumerate(videos):
            ts = video_ts_map[video]
            if ts is None:
                continue
            duration = durations[i]
            if duration <= 0:
                logger.warning(f"无法获取视频时长，跳过: {video.name}")
                continue

            start_ms = int((ts - earliest_ts).total_seconds() * 1000)
            end_ms = start_ms + int(duration * 1000)
            ass_output = str(session_path / f"{video.stem}.ass")

            segments.append(SegmentInfo(
                recording_file_id=video.stem,  # 用作输出文件名
                start_ms=start_ms,
                end_ms=end_ms,
                output_path=ass_output,
            ))

        if segments:
            generated = await generator.generate_segment_ass(
                jsonl_path=str(jsonl_path),
                output_dir=str(session_path),
                segments=segments,
                video_width=req.video_width,
                video_height=req.video_height,
            )
    else:
        # 单文件或无时间戳：生成完整 ASS 并放到会话目录
        if len(videos) == 1:
            output_path = session_path / f"{videos[0].stem}.ass"
        else:
            output_path = session_path / "danmaku" / "danmaku.ass"

        ass_path = await generator.generate_from_jsonl(
            jsonl_path=str(jsonl_path),
            ass_path=str(output_path),
            video_width=req.video_width,
            video_height=req.video_height,
        )
        generated = [ass_path]

    # 统计弹幕条数
    danmaku_count = 0
    try:
        danmaku_count = await _count_jsonl_lines(jsonl_path)
    except OSError:
        pass

    logger.info(
        f"会话 ASS 生成完成: {req.session_id} → {len(generated)} 个文件 ({danmaku_count} 条弹幕)"
    )
    return {
        "status": "completed",
        "generated_files": generated,
        "danmaku_count": danmaku_count,
    }

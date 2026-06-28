"""ASS 生成 API。"""
from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..core.ass_generator import DanmakuAssGenerator
from ..db import tasks_dao
from ..deps import get_db_conn, get_queue
from ..models.task import Task, TaskType
from ..queue.task_queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


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

"""压制任务 API。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..db import tasks_dao
from ..deps import get_db_conn, get_queue
from ..models.task import Task, TaskType
from ..queue.task_queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


class BurnRequest(BaseModel):
    """压制任务请求。"""
    video_path: str = Field(..., description="视频文件绝对路径")
    ass_path: str = Field(..., description="ASS 字幕文件绝对路径")
    output_path: str | None = Field(None, description="输出路径（默认自动生成）")
    encoder: Literal["auto", "nvenc", "cpu"] = Field("auto", description="编码器选择")
    fps: int = Field(30, ge=24, le=60, description="输出帧率")
    offset_ms: int = Field(0, description="弹幕时间偏移量（ms），正值表示视频晚于录制开始")
    callback_url: str | None = Field(None, description="完成回调 URL")
    metadata: dict | None = Field(None, description="透传元数据")

    @field_validator("video_path", "ass_path")
    @classmethod
    def validate_path_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"文件不存在: {v}")
        return v

    @field_validator("video_path")
    @classmethod
    def validate_video_ext(cls, v: str) -> str:
        if Path(v).suffix.lower() not in (".mp4", ".mkv", ".flv", ".ts"):
            raise ValueError(f"不支持的视频格式: {Path(v).suffix}")
        return v


class FreeBurnRequest(BaseModel):
    """自由压制请求（跨会话）。"""
    video_path: str = Field(..., description="视频文件绝对路径")
    jsonl_path: str = Field(..., description="JSONL 弹幕文件绝对路径")
    output_path: str | None = Field(None, description="输出路径")
    video_width: int = Field(1920, description="视频宽度")
    video_height: int = Field(1080, description="视频高度")
    encoder: Literal["auto", "nvenc", "cpu"] = Field("auto")
    fps: int = Field(30, ge=24, le=60)
    offset_ms: int = Field(0, description="弹幕时间偏移量（ms）")
    callback_url: str | None = Field(None)
    metadata: dict | None = Field(None)

    @field_validator("video_path")
    @classmethod
    def validate_video_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"文件不存在: {v}")
        return v

    @field_validator("jsonl_path")
    @classmethod
    def validate_jsonl_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"文件不存在: {v}")
        return v


class BurnResponse(BaseModel):
    """压制任务响应。"""
    task_id: str
    status: str
    message: str


def _default_output_path(video_path: str, suffix: str = "_danmaku") -> str:
    """自动生成输出路径。"""
    p = Path(video_path)
    output_name = f"{p.stem}{suffix}{p.suffix}"
    return str(settings.danmaku_output_dir / output_name)


@router.post("/api/burn", response_model=BurnResponse)
async def create_burn_task(
    req: BurnRequest,
    queue: TaskQueue = Depends(get_queue),
    db: aiosqlite.Connection = Depends(get_db_conn),
) -> BurnResponse:
    """创建压制任务。"""
    output_path = req.output_path or _default_output_path(req.video_path)

    task = Task(
        type=TaskType.BURN,
        video_path=req.video_path,
        ass_path=req.ass_path,
        output_path=output_path,
        encoder=req.encoder,
        fps=req.fps,
        offset_ms=req.offset_ms,
        callback_url=req.callback_url,
        metadata=json.dumps(req.metadata) if req.metadata else None,
    )

    await tasks_dao.insert(db, task)
    await queue.put(task)

    logger.info(f"创建压制任务: {task.id}, video={req.video_path}")
    return BurnResponse(task_id=task.id, status="queued", message="任务已加入队列")


@router.post("/api/burn/free", response_model=BurnResponse)
async def create_free_burn_task(
    req: FreeBurnRequest,
    queue: TaskQueue = Depends(get_queue),
    db: aiosqlite.Connection = Depends(get_db_conn),
) -> BurnResponse:
    """创建自由压制任务（跨会话）。"""
    output_path = req.output_path or _default_output_path(req.video_path, "_free_danmaku")

    task = Task(
        type=TaskType.FREE_BURN,
        video_path=req.video_path,
        jsonl_path=req.jsonl_path,
        output_path=output_path,
        encoder=req.encoder,
        fps=req.fps,
        offset_ms=req.offset_ms,
        video_width=req.video_width,
        video_height=req.video_height,
        callback_url=req.callback_url,
        metadata=json.dumps(req.metadata) if req.metadata else None,
    )

    await tasks_dao.insert(db, task)
    await queue.put(task)

    logger.info(f"创建自由压制任务: {task.id}")
    return BurnResponse(task_id=task.id, status="queued", message="任务已加入队列")


@router.post("/api/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    queue: TaskQueue = Depends(get_queue),
) -> dict:
    """取消任务。"""
    success = await queue.cancel(task_id)
    if not success:
        raise HTTPException(400, "任务不存在或无法取消")
    return {"task_id": task_id, "status": "cancelled"}


@router.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: str,
    db: aiosqlite.Connection = Depends(get_db_conn),
) -> dict:
    """删除任务记录。"""
    success = await tasks_dao.delete(db, task_id)
    if not success:
        raise HTTPException(404, "任务不存在")
    return {"task_id": task_id, "deleted": True}


# ── 压制测试 ──

BURN_TEST_DURATION = 60.0  # 测试压制时长（秒）


class BurnTestRequest(BaseModel):
    """压制测试请求。"""
    video_path: str = Field(..., description="视频文件绝对路径")
    ass_path: str = Field(..., description="ASS 字幕文件绝对路径")
    encoder: Literal["auto", "nvenc", "cpu"] = Field("auto", description="编码器选择")
    fps: int = Field(30, ge=24, le=60, description="输出帧率")
    offset_ms: int = Field(0, description="弹幕时间偏移量（ms）")

    @field_validator("video_path", "ass_path")
    @classmethod
    def validate_path_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"文件不存在: {v}")
        return v

    @field_validator("video_path")
    @classmethod
    def validate_video_ext(cls, v: str) -> str:
        if Path(v).suffix.lower() not in (".mp4", ".mkv", ".flv", ".ts"):
            raise ValueError(f"不支持的视频格式: {Path(v).suffix}")
        return v


def _test_output_path(task_id: str) -> str:
    """生成测试压制输出文件路径。"""
    test_dir = settings.cache_dir / "test_preview"
    test_dir.mkdir(parents=True, exist_ok=True)
    return str(test_dir / f"{task_id}.mp4")


@router.post("/api/burn/test", response_model=BurnResponse)
async def create_burn_test_task(
    req: BurnTestRequest,
    queue: TaskQueue = Depends(get_queue),
    db: aiosqlite.Connection = Depends(get_db_conn),
) -> BurnResponse:
    """创建压制测试任务（仅编码前 60 秒）。"""
    task = Task(
        type=TaskType.BURN_TEST,
        video_path=req.video_path,
        ass_path=req.ass_path,
        output_path="",  # 稍后由 task_id 生成
        encoder=req.encoder,
        fps=req.fps,
        offset_ms=req.offset_ms,
        duration_limit=BURN_TEST_DURATION,
    )
    task.output_path = _test_output_path(task.id)

    await tasks_dao.insert(db, task)
    await queue.put(task)

    logger.info(f"创建压制测试任务: {task.id}, video={req.video_path}")
    return BurnResponse(task_id=task.id, status="queued", message="测试任务已加入队列")


@router.get("/api/burn/test/{task_id}/video")
async def stream_test_video(
    task_id: str,
    db: aiosqlite.Connection = Depends(get_db_conn),
):
    """返回测试压制视频文件，支持 Range 请求以便在浏览器中拖动预览。"""
    task = await tasks_dao.get(db, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.type != TaskType.BURN_TEST:
        raise HTTPException(400, "非测试压制任务")

    video_path = Path(task.output_path)
    if not video_path.exists():
        raise HTTPException(404, "测试视频文件不存在")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=video_path.name,
    )

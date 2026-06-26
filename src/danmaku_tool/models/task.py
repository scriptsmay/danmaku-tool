"""任务数据模型。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class TaskType(StrEnum):
    """任务类型。"""
    BURN = "burn"
    ASS_GENERATE = "ass_generate"
    FREE_BURN = "free_burn"
    BURN_TEST = "burn_test"


class TaskStatus(StrEnum):
    """任务状态。"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """压制任务。"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    type: TaskType = TaskType.BURN
    status: TaskStatus = TaskStatus.QUEUED

    # 输入
    video_path: str | None = None
    ass_path: str | None = None
    jsonl_path: str | None = None
    output_path: str | None = None
    encoder: str = "auto"
    fps: int = 30
    offset_ms: int = 0
    video_width: int | None = None
    video_height: int | None = None
    duration_limit: float | None = None  # 压制时长限制（秒），用于测试压制

    # 回调
    callback_url: str | None = None
    metadata: str | None = None  # JSON 字符串

    # 结果
    progress: float = 0.0
    speed: str | None = None
    output_size: int | None = None
    error: str | None = None

    # 时间戳
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None

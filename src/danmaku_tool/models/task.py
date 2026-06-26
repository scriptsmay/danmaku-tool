"""任务数据模型。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    """任务类型。"""
    BURN = "burn"
    ASS_GENERATE = "ass_generate"
    FREE_BURN = "free_burn"


class TaskStatus(str, Enum):
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
    video_path: Optional[str] = None
    ass_path: Optional[str] = None
    jsonl_path: Optional[str] = None
    output_path: Optional[str] = None
    encoder: str = "auto"
    fps: int = 30
    offset_ms: int = 0
    video_width: Optional[int] = None
    video_height: Optional[int] = None

    # 回调
    callback_url: Optional[str] = None
    metadata: Optional[str] = None  # JSON 字符串

    # 结果
    progress: float = 0.0
    speed: Optional[str] = None
    output_size: Optional[int] = None
    error: Optional[str] = None

    # 时间戳
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

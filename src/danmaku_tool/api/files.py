"""文件浏览器 API。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class FileItem(BaseModel):
    """文件/目录项。"""
    name: str
    path: str
    is_dir: bool
    size: int | None
    ext: str | None


class BrowseResponse(BaseModel):
    """浏览结果。"""
    current: str
    parent: str | None
    entries: list[FileItem]


class OffsetResponse(BaseModel):
    """偏移量计算结果。"""
    offset_ms: int
    video_time: str | None
    first_segment_time: str | None
    video_name: str
    first_segment_name: str | None
    message: str


# 匹配文件名中的时间戳：20260625_215745 或 20260625-215745
_TS_PATTERN = re.compile(r"(\d{8})[_-](\d{6})")
VIDEO_EXTS = {".mp4", ".mkv", ".flv", ".ts"}


def _parse_ts_from_filename(name: str) -> datetime | None:
    """从文件名解析时间戳。"""
    m = _TS_PATTERN.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _format_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _check_path_allowed(path: Path) -> None:
    """检查路径是否在允许的根目录下。"""
    resolved = str(path.resolve())
    allowed = any(
        resolved.startswith(str(Path(root).resolve()))
        or str(path).startswith(root)
        for root in settings.allowed_roots
    )
    if not allowed:
        raise HTTPException(403, "无权访问此目录")


@router.get("/api/files/browse", response_model=BrowseResponse)
async def browse_files(
    path: str = Query(default="", description="目录路径，为空时列出根目录"),
    filter_ext: str = Query(default="", description="过滤扩展名，逗号分隔，如 .mp4,.mkv"),
) -> BrowseResponse:
    """浏览本地文件系统。

    安全规则：
    1. 只允许浏览 settings.allowed_roots 中列出的目录
    2. 禁止路径穿越（..）
    3. 不返回隐藏文件（以 . 开头）
    """
    if not path:
        entries = [
            FileItem(name=root, path=root, is_dir=True, size=None, ext=None)
            for root in settings.allowed_roots
            if Path(root).exists()
        ]
        return BrowseResponse(current="", parent=None, entries=entries)

    # 安全检查：路径穿越
    if ".." in path:
        raise HTTPException(400, "禁止路径穿越")

    target = Path(path).resolve()
    _check_path_allowed(target)

    if not target.is_dir():
        raise HTTPException(400, "路径不是目录")

    # 列出目录内容
    entries: list[FileItem] = []
    try:
        items = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        raise HTTPException(403, "无权访问此目录")

    filter_exts = {e.strip().lower() for e in filter_ext.split(",") if e.strip()} if filter_ext else set()

    for item in items:
        if item.name.startswith("."):
            continue
        ext = item.suffix.lower() if item.is_file() else None
        if filter_exts and item.is_file() and ext not in filter_exts:
            continue
        try:
            size = item.stat().st_size if item.is_file() else None
        except (OSError, PermissionError):
            size = None
        entries.append(FileItem(
            name=item.name,
            path=str(item),
            is_dir=item.is_dir(),
            size=size,
            ext=ext,
        ))

    parent = str(target.parent) if str(target.parent) != str(target) else None
    return BrowseResponse(current=str(target), parent=parent, entries=entries)


@router.get("/api/files/calc-offset", response_model=OffsetResponse)
async def calc_offset(
    video_path: str = Query(..., description="视频文件绝对路径"),
) -> OffsetResponse:
    """根据视频文件名时间戳自动计算弹幕偏移量。

    逻辑：
    1. 从视频文件名解析时间戳（如 20260625_215745.ts）
    2. 扫描同目录下所有视频文件，找到最早的一个
    3. offset_ms = (当前视频时间 - 最早视频时间) 的毫秒数
    """
    if ".." in video_path:
        raise HTTPException(400, "禁止路径穿越")

    video = Path(video_path)
    _check_path_allowed(video)

    if not video.exists():
        raise HTTPException(404, "文件不存在")

    video_ts = _parse_ts_from_filename(video.name)
    if not video_ts:
        return OffsetResponse(
            offset_ms=0,
            video_time=None,
            first_segment_time=None,
            video_name=video.name,
            first_segment_name=None,
            message="无法从文件名解析时间戳，偏移量设为 0",
        )

    # 扫描同目录下所有视频文件，找最早的
    parent = video.parent
    earliest_ts: datetime | None = None
    earliest_name: str | None = None

    try:
        for item in parent.iterdir():
            if item.is_file() and item.suffix.lower() in VIDEO_EXTS:
                ts = _parse_ts_from_filename(item.name)
                if ts and (earliest_ts is None or ts < earliest_ts):
                    earliest_ts = ts
                    earliest_name = item.name
    except PermissionError:
        pass

    if not earliest_ts or earliest_ts == video_ts:
        return OffsetResponse(
            offset_ms=0,
            video_time=video_ts.strftime("%Y-%m-%d %H:%M:%S"),
            first_segment_time=video_ts.strftime("%Y-%m-%d %H:%M:%S") if earliest_ts else None,
            video_name=video.name,
            first_segment_name=earliest_name,
            message="当前文件即为第一段，偏移量为 0",
        )

    delta_ms = int((video_ts - earliest_ts).total_seconds() * 1000)
    return OffsetResponse(
        offset_ms=delta_ms,
        video_time=video_ts.strftime("%Y-%m-%d %H:%M:%S"),
        first_segment_time=earliest_ts.strftime("%Y-%m-%d %H:%M:%S"),
        video_name=video.name,
        first_segment_name=earliest_name,
        message=f"从 {earliest_name} 到 {video.name} 的偏移",
    )

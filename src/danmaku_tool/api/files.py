"""文件浏览器 API。"""
from __future__ import annotations

import logging
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


def _format_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


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

    # 安全检查：必须在允许的根目录下
    allowed = any(str(target).startswith(root) for root in settings.allowed_roots)
    if not allowed:
        raise HTTPException(403, "无权访问此目录")

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

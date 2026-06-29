"""共享工具函数。"""
from __future__ import annotations

import re
from datetime import datetime

VIDEO_EXTS = {".ts", ".mp4", ".mkv", ".flv"}

# 匹配文件名中的时间戳：20260625_215745 或 20260625-215745
_TS_PATTERN = re.compile(r"(\d{8})[_-](\d{6})")


def parse_ts_from_filename(name: str) -> datetime | None:
    """从文件名解析时间戳（如 20260625_215745）。"""
    m = _TS_PATTERN.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None

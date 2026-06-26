"""健康检查 + 编码器能力。"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..core.capabilities import probe
from ..core.font_checker import check_cjk_fonts
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/health")
async def health_check() -> dict:
    """健康检查 + 编码器能力 + 字体状态。"""
    caps = await probe(settings.ffmpeg_path)
    font_info = await check_cjk_fonts()

    return {
        "status": "ok",
        "capabilities": {
            "nvenc_available": caps.nvenc_available,
            "qsv_available": caps.qsv_available,
            "libx264_available": caps.libx264_available,
            "subtitles_filter": caps.subtitles_filter,
            "nvenc_encoders": caps.nvenc_encoders,
            "best_encoder": caps.best_encoder,
            "encoder_label": caps.encoder_label,
        },
        "fonts": font_info,
        "config": {
            "output_dir": str(settings.danmaku_output_dir),
            "fps": settings.danmaku_burn_fps,
            "max_concurrent_tasks": settings.max_concurrent_tasks,
            "cache_enabled": settings.cache_enabled,
            "cache_dir": str(settings.cache_dir),
        },
    }

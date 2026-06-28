"""健康检查 + 编码器能力 + 字体设置。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..core.capabilities import probe
from ..core.font_checker import check_cjk_fonts, list_system_fonts

logger = logging.getLogger(__name__)
router = APIRouter()


class FontUpdateRequest(BaseModel):
    """字体更新请求。"""
    font_family: str


class DanmakuSettingsRequest(BaseModel):
    """弹幕样式设置请求（所有字段可选，仅更新提供的字段）。"""
    font_family: str | None = None
    font_size: int | None = None
    opacity: float | None = None
    outline_width: int | None = None
    max_per_second: int | None = None


# 弹幕样式字段 → .env key 映射
_STYLE_FIELDS = {
    "font_family": "DANMAKU_FONT_FAMILY",
    "font_size": "DANMAKU_FONT_SIZE",
    "opacity": "DANMAKU_OPACITY",
    "outline_width": "DANMAKU_OUTLINE_WIDTH",
    "max_per_second": "DANMAKU_MAX_PER_SECOND",
}


def _update_env_file(key: str, value: str) -> bool:
    """原子写入/更新 .env 文件中的单个配置项。"""
    env_path = Path(".env")
    lines: list[str] = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        prefix = f"{key}="
        for i, line in enumerate(lines):
            if line.strip().startswith(prefix):
                lines[i] = f"{key}={value}"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}")
    try:
        tmp = env_path.with_suffix(".env.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(env_path)
        return True
    except OSError:
        logger.warning(f"无法写入 .env 文件: {env_path}")
        return False


def _update_env_batch(updates: dict[str, str]) -> bool:
    """批量更新 .env 文件中的多个配置项（原子写入）。"""
    env_path = Path(".env")
    lines: list[str] = []
    existing_keys: set[str] = set()
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            for key in updates:
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={updates[key]}"
                    existing_keys.add(key)
                    break
    for key, value in updates.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")
    try:
        tmp = env_path.with_suffix(".env.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(env_path)
        return True
    except OSError:
        logger.warning(f"无法写入 .env 文件: {env_path}")
        return False


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
            "suffix": settings.danmaku_burn_suffix,
            "fps": settings.danmaku_burn_fps,
            "max_concurrent_tasks": settings.max_concurrent_tasks,
            "cache_enabled": settings.cache_enabled,
            "cache_dir": str(settings.cache_dir),
            "font_family": settings.font_family,
            "font_size": settings.font_size,
            "opacity": settings.opacity,
            "outline_width": settings.outline_width,
            "max_per_second": settings.max_per_second,
        },
    }


@router.get("/api/fonts")
async def list_fonts() -> dict:
    """列出系统已安装的 CJK 字体和当前选中字体。"""
    fonts = await list_system_fonts()
    return {"fonts": fonts, "current": settings.font_family}


@router.put("/api/settings/font")
async def update_font(req: FontUpdateRequest) -> dict:
    """更新默认字体并持久化到 .env 文件。"""
    new_font = req.font_family.strip()
    if not new_font:
        return {"font_family": settings.font_family, "persisted": False, "error": "字体名称不能为空"}

    settings.font_family = new_font
    persisted = _update_env_file("DANMAKU_FONT_FAMILY", new_font)
    logger.info(f"字体已更新: {new_font} (persisted={persisted})")
    return {"font_family": new_font, "persisted": persisted}


@router.get("/api/settings")
async def get_danmaku_settings() -> dict:
    """获取当前弹幕样式配置。"""
    return {
        "font_family": settings.font_family,
        "font_size": settings.font_size,
        "opacity": settings.opacity,
        "outline_width": settings.outline_width,
        "max_per_second": settings.max_per_second,
    }


@router.put("/api/settings")
async def update_danmaku_settings(req: DanmakuSettingsRequest) -> dict:
    """批量更新弹幕样式设置并持久化到 .env 文件。"""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"updated": {}, "persisted": False, "error": "未提供任何更新字段"}

    # 校验
    errors = []
    if "font_family" in updates and not updates["font_family"].strip():
        errors.append("字体名称不能为空")
    if "font_size" in updates and not (8 <= updates["font_size"] <= 120):
        errors.append("字体大小需在 8-120 之间")
    if "opacity" in updates and not (0.0 <= updates["opacity"] <= 1.0):
        errors.append("不透明度需在 0-1 之间")
    if "outline_width" in updates and not (0 <= updates["outline_width"] <= 10):
        errors.append("描边宽度需在 0-10 之间")
    if "max_per_second" in updates and not (1 <= updates["max_per_second"] <= 60):
        errors.append("每秒弹幕上限需在 1-60 之间")
    if errors:
        return {"updated": {}, "persisted": False, "error": "; ".join(errors)}

    # 写入内存
    for key, value in updates.items():
        if key == "font_family":
            value = value.strip()
        setattr(settings, key, value)

    # 持久化到 .env
    env_updates = {}
    for key, value in updates.items():
        env_key = _STYLE_FIELDS.get(key)
        if env_key:
            env_updates[env_key] = str(value)
    persisted = _update_env_batch(env_updates) if env_updates else False

    logger.info(f"弹幕样式已更新: {list(updates.keys())} (persisted={persisted})")
    return {"updated": updates, "persisted": persisted}

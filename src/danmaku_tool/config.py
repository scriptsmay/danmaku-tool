"""danmaku-tool 配置模块。

优先级：环境变量 > .env 文件 > 默认值
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings
from pydantic_settings.sources import DotEnvSettingsSource


def _default_output_dir() -> Path:
    """根据平台返回默认输出目录。"""
    if sys.platform == "win32":
        return Path(r"C:\DanmakuOutput")
    return Path.home() / "DanmakuOutput"


def _default_allowed_roots() -> list[str]:
    """根据平台返回默认允许浏览的根目录。"""
    if sys.platform == "win32":
        return [r"C:\Recordings", r"C:\DanmakuOutput", r"D:\Videos"]
    return [str(Path.home())]


def _parse_csv_or_json(v: Any) -> list[str]:
    """将逗号分隔字符串或 JSON 数组解析为 list[str]。"""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        return [r.strip() for r in v.split(",") if r.strip()]
    return [str(v)]


class _LenientDotEnvSource(DotEnvSettingsSource):
    """JSON 解析失败时返回原始字符串，交给 BeforeValidator 处理。"""

    def prepare_field_value(self, field_name: str, field, value, value_is_complex: bool):
        try:
            return super().prepare_field_value(field_name, field, value, value_is_complex)
        except Exception:
            return value


class Settings(BaseSettings):
    """应用配置，支持 .env 文件和环境变量。"""

    # ── 服务 ──
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # ── FFmpeg ──
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    # ── 字体 ──
    font_family: str = "Noto Sans CJK SC"

    # ── 弹幕压制 ──
    danmaku_output_dir: Path = Field(default_factory=_default_output_dir)
    danmaku_burn_fps: int = Field(default=30, ge=24, le=60)
    danmaku_burn_suffix: str = "_danmaku"

    # ── 本地缓存 ──
    cache_dir: Path = Field(default=Path("data/cache"))
    cache_enabled: bool = Field(default=True)

    # ── 任务队列 ──
    max_concurrent_tasks: int = 1  # GPU 独占，默认 1

    # ── 文件浏览器安全（JSON 数组或逗号分隔）──
    allowed_roots: Annotated[list[str], BeforeValidator(_parse_csv_or_json)] = Field(
        default_factory=_default_allowed_roots
    )

    # ── Webhook（可选，联动 live-recorder-server）──
    webhook_enabled: bool = False
    webhook_callback_url: str = ""

    # ── 数据库 ──
    db_path: Path = Path("data/danmaku_tool.db")

    # ── 日志 ──
    log_dir: Path = Path("data/logs")
    log_level: str = "INFO"

    model_config = {"env_prefix": "DANMAKU_", "env_file": ".env", "env_file_encoding": "utf-8"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            _LenientDotEnvSource(settings_cls, env_prefix="DANMAKU_", env_file=".env"),
        )


settings = Settings()

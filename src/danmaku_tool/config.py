"""danmaku-tool 配置模块。

优先级：环境变量 > .env 文件 > 默认值
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持 .env 文件和环境变量。"""

    # ── 服务 ──
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # ── FFmpeg ──
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    # ── 弹幕压制 ──
    danmaku_output_dir: Path = Path(r"C:\DanmakuOutput")
    danmaku_burn_fps: int = Field(default=30, ge=24, le=60)
    danmaku_burn_suffix: str = "_danmaku.mp4"

    # ── 任务队列 ──
    max_concurrent_tasks: int = 1  # GPU 独占，默认 1

    # ── 文件浏览器安全 ──
    allowed_roots: list[str] = Field(
        default_factory=lambda: [r"C:\Recordings", r"C:\DanmakuOutput", r"D:\Videos"]
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


settings = Settings()

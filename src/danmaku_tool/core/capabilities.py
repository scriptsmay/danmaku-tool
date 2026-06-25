"""FFmpeg 编码器和滤镜能力探测。"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Capabilities:
    """FFmpeg 能力。"""
    nvenc_available: bool = False
    qsv_available: bool = False
    libx264_available: bool = False
    subtitles_filter: bool = False
    nvenc_encoders: list[str] = field(default_factory=list)

    @property
    def best_encoder(self) -> str:
        """返回最佳可用编码器。"""
        if self.nvenc_available:
            return "nvenc"
        if self.qsv_available:
            return "qsv"
        return "cpu"

    @property
    def encoder_label(self) -> str:
        """返回人类可读的编码器名称。"""
        mapping = {
            "nvenc": "NVENC (GPU)",
            "qsv": "QSV (GPU)",
            "cpu": "libx264 (CPU)",
        }
        return mapping.get(self.best_encoder, self.best_encoder)


async def probe(ffmpeg_path: str = "ffmpeg") -> Capabilities:
    """探测 FFmpeg 编码器能力。"""
    caps = Capabilities()

    # 1. 探测可用编码器
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-encoders",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        encoders_text = stdout.decode(errors="ignore")

        caps.nvenc_available = "h264_nvenc" in encoders_text
        caps.qsv_available = "h264_qsv" in encoders_text
        caps.libx264_available = "libx264" in encoders_text

        if caps.nvenc_available:
            caps.nvenc_encoders = [e for e in ["h264_nvenc", "hevc_nvenc"] if e in encoders_text]
    except FileNotFoundError:
        logger.warning(f"FFmpeg 未找到: {ffmpeg_path}")
    except Exception as e:
        logger.warning(f"编码器探测失败: {e}")

    # 2. 探测滤镜
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-filters",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        filters_text = stdout.decode(errors="ignore")
        caps.subtitles_filter = "subtitles" in filters_text or "ass" in filters_text
    except Exception:
        pass

    logger.info(
        f"编码器探测: nvenc={caps.nvenc_available}, qsv={caps.qsv_available}, "
        f"libx264={caps.libx264_available}, subtitles={caps.subtitles_filter}"
    )
    return caps

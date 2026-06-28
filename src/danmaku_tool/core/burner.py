"""FFmpeg 弹幕压制引擎。支持 NVENC / QSV / CPU 编码器。"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .capabilities import Capabilities, probe

logger = logging.getLogger(__name__)


@dataclass
class BurnResult:
    """压制结果。"""
    success: bool
    output_path: str
    duration_seconds: float
    output_size: int
    encoder_used: str
    error: str | None = None


@dataclass
class BurnProgress:
    """压制进度。"""
    percent: float
    time: str
    speed: str
    size: str
    fps: str


class DanmakuBurner:
    """弹幕压制引擎。

    FFmpeg 滤镜链：
    setpts=PTS-STARTPTS,fps={fps},ass='{escaped_ass_path}',format=yuv420p

    编码器优先级：NVENC > QSV > CPU
    """

    # 编码器参数映射
    ENCODER_ARGS: dict[str, list[str]] = {
        "nvenc": [
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-rc", "constqp",
            "-qp", "23",
            "-b:v", "0",
            "-spatial-aq", "1",
            "-temporal-aq", "1",
        ],
        "qsv": [
            "-c:v", "h264_qsv",
            "-global_quality", "23",
        ],
        "cpu": [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
        ],
    }

    # 字体错误关键词（致命错误，会终止压制）
    FONT_ERROR_PATTERNS = [
        r"fontconfig.*error",
        r"font.*not found",
        r"cannot.*open font",
        r"Font.*not found",
        r"ASS_Event.*error",
    ]

    # 字体警告关键词（仅警告，不终止）
    FONT_WARN_PATTERNS = [
        r"Glyph.*not found",
    ]

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._font_error_re = re.compile("|".join(self.FONT_ERROR_PATTERNS), re.IGNORECASE)
        self._font_warn_re = re.compile("|".join(self.FONT_WARN_PATTERNS), re.IGNORECASE)
        self._caps: Capabilities | None = None

    async def get_capabilities(self) -> Capabilities:
        """获取编码器能力（缓存）。"""
        if self._caps is None:
            self._caps = await probe(self.ffmpeg_path)
        return self._caps

    async def get_video_duration(self, video_path: str) -> float:
        """获取视频时长（秒）。"""
        proc = await asyncio.create_subprocess_exec(
            self.ffprobe_path,
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            return float(stdout.decode().strip())
        except ValueError:
            return 0.0

    async def burn(
        self,
        video_path: str,
        ass_path: str,
        output_path: str,
        encoder: str = "auto",
        fps: int = 30,
        duration_limit: float | None = None,
        on_progress: Callable[[BurnProgress], None] | None = None,
    ) -> BurnResult:
        """执行弹幕压制。

        duration_limit: 压制时长限制（秒），用于测试压制。设置后 FFmpeg 只编码指定时长。
        """
        if not ass_path:
            return BurnResult(
                success=False,
                output_path=output_path,
                duration_seconds=0.0,
                output_size=0,
                encoder_used="none",
                error="ASS 路径为空，无法执行压制",
            )

        # 确保输出目录存在
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 解析编码器
        actual_encoder = await self._resolve_encoder(encoder)
        encoder_args = self.ENCODER_ARGS[actual_encoder]

        # 获取视频时长
        duration = await self.get_video_duration(video_path)

        # 测试压制时，使用 duration_limit 作为有效时长（用于进度计算）
        effective_duration = duration_limit if duration_limit else duration

        # 构建 FFmpeg 参数
        # Windows 路径转义：冒号前加反斜杠，反斜杠替换为正斜杠
        escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")

        filter_chain = (
            f"setpts=PTS-STARTPTS,"
            f"fps={fps},"
            f"ass='{escaped_ass}',"
            f"format=yuv420p"
        )

        args = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", filter_chain,
            *encoder_args,
            "-c:a", "copy",
            "-movflags", "+faststart",
        ]

        # 测试压制：限制编码时长
        if duration_limit:
            args.extend(["-t", str(duration_limit)])

        args.append(output_path)

        logger.info(f"开始压制: encoder={actual_encoder}, fps={fps}")
        logger.debug(f"FFmpeg 命令: {' '.join(args)}")

        # 执行
        start_time = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        font_check_deadline = 30.0
        stderr_lines: list[str] = []
        partial = b""

        try:
            if proc.stderr is None:
                raise RuntimeError("FFmpeg stderr pipe 未创建")

            # 用 read(4096) 按块读取，避免 Windows pipe 缓冲导致 async for line 不触发
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                partial += chunk
                while b"\n" in partial:
                    raw_line, partial = partial.split(b"\n", 1)
                    decoded = raw_line.decode(errors="ignore").strip()
                    if not decoded:
                        continue

                    stderr_lines.append(decoded)

                    # 字体错误检测（前 30 秒）
                    elapsed = time.monotonic() - start_time
                    if elapsed < font_check_deadline:
                        if self._font_error_re.search(decoded):
                            proc.kill()
                            return BurnResult(
                                success=False,
                                output_path=output_path,
                                duration_seconds=elapsed,
                                output_size=0,
                                encoder_used=actual_encoder,
                                error=f"字体错误: {decoded}",
                            )
                        if self._font_warn_re.search(decoded):
                            logger.warning(f"字体警告: {decoded}")

                    # 进度解析
                    progress = self._parse_progress(decoded, effective_duration)
                    if progress and on_progress:
                        on_progress(progress)

            # 处理最后一个没有换行的残留行
            if partial:
                decoded = partial.decode(errors="ignore").strip()
                if decoded:
                    stderr_lines.append(decoded)
                    progress = self._parse_progress(decoded, effective_duration)
                    if progress and on_progress:
                        on_progress(progress)

        except Exception as e:
            logger.warning(f"stderr 读取异常: {e}")
            try:
                _, remaining = await proc.communicate()
                if remaining:
                    for line in remaining.splitlines()[-5:]:
                        stderr_lines.append(line.decode(errors="ignore").strip())
            except Exception:
                pass

        await proc.wait()
        elapsed = time.monotonic() - start_time

        if proc.returncode != 0:
            # 显示最后 5 行 stderr，提供更多错误上下文
            tail = stderr_lines[-5:] if len(stderr_lines) > 5 else stderr_lines
            error_msg = " | ".join(tail) if tail else "unknown"
            logger.error(f"压制失败 (exit={proc.returncode}): {error_msg}")
            return BurnResult(
                success=False,
                output_path=output_path,
                duration_seconds=elapsed,
                output_size=0,
                encoder_used=actual_encoder,
                error=f"FFmpeg 退出码 {proc.returncode}: {error_msg}",
            )

        output_size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
        logger.info(f"压制完成: {elapsed:.1f}s, encoder={actual_encoder}, size={output_size}")

        return BurnResult(
            success=True,
            output_path=output_path,
            duration_seconds=elapsed,
            output_size=output_size,
            encoder_used=actual_encoder,
        )

    async def _resolve_encoder(self, encoder: str) -> str:
        """解析编码器选择。auto 时按优先级探测。"""
        if encoder != "auto":
            return encoder
        caps = await self.get_capabilities()
        return caps.best_encoder

    def _parse_progress(self, line: str, total_duration: float) -> BurnProgress | None:
        """从 FFmpeg stderr 解析进度。"""
        time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
        if not time_match:
            return None

        time_str = time_match.group(1)
        current_sec = _time_to_seconds(time_str)
        percent = min(100.0, (current_sec / total_duration * 100)) if total_duration > 0 else 0

        speed_match = re.search(r"speed=\s*([\d.]+)x", line)
        speed = f"{speed_match.group(1)}x" if speed_match else ""

        size_match = re.search(r"size=\s*(\d+)(\w+)", line)
        size = f"{size_match.group(1)}{size_match.group(2)}" if size_match else ""

        fps_match = re.search(r"fps=\s*(\d+)", line)
        fps = fps_match.group(1) if fps_match else ""

        return BurnProgress(percent=percent, time=time_str, speed=speed, size=size, fps=fps)


def _time_to_seconds(time_str: str) -> float:
    """HH:MM:SS.xx -> 秒数。"""
    parts = time_str.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

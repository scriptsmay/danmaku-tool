"""编码器探测测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from danmaku_tool.core.capabilities import Capabilities, probe


class TestCapabilities:
    """Capabilities 数据类测试。"""

    def test_best_encoder_nvenc(self):
        caps = Capabilities(nvenc_available=True, libx264_available=True)
        assert caps.best_encoder == "nvenc"

    def test_best_encoder_qsv(self):
        caps = Capabilities(qsv_available=True, libx264_available=True)
        assert caps.best_encoder == "qsv"

    def test_best_encoder_cpu(self):
        caps = Capabilities(libx264_available=True)
        assert caps.best_encoder == "cpu"

    def test_encoder_label(self):
        caps = Capabilities(nvenc_available=True)
        assert caps.encoder_label == "NVENC (GPU)"

        caps2 = Capabilities(libx264_available=True)
        assert caps2.encoder_label == "libx264 (CPU)"


@pytest.mark.asyncio
async def test_probe_nvenc_available():
    """模拟 FFmpeg 输出包含 NVENC。"""
    encoders_output = b" V..... h264_nvenc         NVIDIA NVENC H.264 Encoder"
    filters_output = b" ... subtitles         ... ASS/SRT/SSA subtitles"

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(encoders_output, b""))

    mock_proc2 = AsyncMock()
    mock_proc2.communicate = AsyncMock(return_value=(filters_output, b""))

    with patch("asyncio.create_subprocess_exec", side_effect=[mock_proc, mock_proc2]):
        caps = await probe("ffmpeg")

    assert caps.nvenc_available is True
    assert caps.libx264_available is False
    assert caps.subtitles_filter is True
    assert "h264_nvenc" in caps.nvenc_encoders


@pytest.mark.asyncio
async def test_probe_ffmpeg_not_found():
    """FFmpeg 不存在时返回默认值。"""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        caps = await probe("nonexistent_ffmpeg")

    assert caps.nvenc_available is False
    assert caps.libx264_available is False

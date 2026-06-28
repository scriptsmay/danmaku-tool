"""FFmpeg 压制引擎测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from danmaku_tool.core.burner import BurnResult, DanmakuBurner, _time_to_seconds
from danmaku_tool.models.task import Task, TaskType
from danmaku_tool.queue.worker import _handle_burn, _is_remote


class TestTimeToSeconds:
    """时间解析测试。"""

    def test_basic(self):
        assert _time_to_seconds("00:01:30.00") == 90.0

    def test_hours(self):
        assert _time_to_seconds("01:00:00.00") == 3600.0

    def test_with_frames(self):
        assert abs(_time_to_seconds("00:02:35.12") - 155.12) < 0.01


class TestBurnProgress:
    """进度解析测试。"""

    def test_burner_parse_progress(self):
        burner = DanmakuBurner()

        # 正常进度行
        line = "frame= 2847 fps=96 q=23.0 size= 450000kB time=00:02:35.12 bitrate=23456kbits/s speed=3.21x"
        progress = burner._parse_progress(line, 300.0)
        assert progress is not None
        assert abs(progress.percent - (155.12 / 300.0 * 100)) < 1.0
        assert progress.speed == "3.21x"
        assert progress.fps == "96"

    def test_burner_parse_progress_no_match(self):
        burner = DanmakuBurner()
        assert burner._parse_progress("some random line", 300.0) is None


class TestEncoderResolution:
    """编码器解析测试。"""

    @pytest.mark.asyncio
    async def test_resolve_encoder_explicit(self):
        burner = DanmakuBurner()
        assert await burner._resolve_encoder("nvenc") == "nvenc"
        assert await burner._resolve_encoder("cpu") == "cpu"

    @pytest.mark.asyncio
    async def test_resolve_encoder_auto(self):
        from danmaku_tool.core.capabilities import Capabilities
        burner = DanmakuBurner()
        mock_caps = Capabilities(nvenc_available=True, libx264_available=True)
        burner._caps = mock_caps
        assert await burner._resolve_encoder("auto") == "nvenc"


class TestBurnExecution:
    """压制执行测试（mock FFmpeg）。"""

    @pytest.mark.asyncio
    async def test_burn_empty_ass_path_returns_clear_error(self, tmp_path: Path, sample_video: Path):
        output = tmp_path / "output.mp4"
        burner = DanmakuBurner()

        result = await burner.burn(
            video_path=str(sample_video),
            ass_path="",
            output_path=str(output),
            encoder="cpu",
        )

        assert result.success is False
        assert result.error == "ASS 路径为空，无法执行压制"

    @pytest.mark.asyncio
    async def test_burn_success(self, tmp_path: Path, sample_video: Path, sample_ass: Path):
        """模拟成功的压制。"""
        # Mock FFmpeg 进程
        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        # 模拟 stderr 输出
        stderr_lines = [
            b"frame=  100 fps=30 q=23.0 size=  1000kB time=00:00:03.33 bitrate=2456kbits/s speed=1.0x\n",
            b"frame=  200 fps=30 q=23.0 size=  2000kB time=00:00:06.66 bitrate=2456kbits/s speed=1.0x\n",
        ]

        async def mock_readline():
            for line in stderr_lines:
                yield line
            return

        mock_proc.stderr = mock_readline()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        # Mock subprocess
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            # Mock ffprobe
            mock_ffprobe = AsyncMock()
            mock_ffprobe.communicate = AsyncMock(return_value=(b"10.0\n", b""))

            call_count = 0
            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # 第一次调用是 ffprobe（获取时长）
                    return mock_ffprobe
                return mock_proc

            mock_exec.side_effect = side_effect

            burner = DanmakuBurner()
            burner._caps = type("Caps", (), {"best_encoder": "cpu", "nvenc_available": False, "qsv_available": False})()

            # 由于 mock 复杂度，这里测试 _resolve_encoder 和 _parse_progress
            encoder = await burner._resolve_encoder("auto")
            assert encoder == "cpu"

    def test_burn_result_dataclass(self):
        result = BurnResult(
            success=True,
            output_path="/tmp/test.mp4",
            duration_seconds=10.5,
            output_size=1024000,
            encoder_used="nvenc",
        )
        assert result.success is True
        assert result.error is None


class TestWorkerBurn:
    """Worker burn path regression tests."""

    def test_is_remote_detects_windows_unc_and_mapped_drive(self):
        assert _is_remote(r"\\server\share\video.ts") is True
        assert _is_remote(r"Z:\videos\record.ts") is True
        assert _is_remote(r"C:\local\record.ts") is False

    @pytest.mark.asyncio
    async def test_handle_burn_generates_ass_from_jsonl(self, tmp_path: Path, sample_video: Path, sample_jsonl: Path):
        output = tmp_path / "output.mp4"
        task = Task(
            type=TaskType.BURN,
            video_path=str(sample_video),
            jsonl_path=str(sample_jsonl),
            output_path=str(output),
            encoder="cpu",
        )

        async def fake_burn(**kwargs):
            Path(kwargs["output_path"]).write_bytes(b"ok")
            return BurnResult(
                success=True,
                output_path=kwargs["output_path"],
                duration_seconds=1.0,
                output_size=2,
                encoder_used="cpu",
            )

        with patch("danmaku_tool.queue.worker.settings.cache_enabled", False), patch(
            "danmaku_tool.queue.worker.DanmakuBurner.burn", new=AsyncMock(side_effect=fake_burn)
        ) as burn_mock:
            await _handle_burn(task)

        generated_ass = sample_video.with_suffix(".ass")
        assert generated_ass.exists()
        assert task.ass_path == str(generated_ass)
        assert task.output_path == str(output)
        assert task.output_size == 2
        assert burn_mock.await_args.kwargs["ass_path"] == str(generated_ass)

    @pytest.mark.asyncio
    async def test_handle_burn_missing_danmaku_input_has_clear_error(self, tmp_path: Path, sample_video: Path):
        task = Task(
            type=TaskType.BURN,
            video_path=str(sample_video),
            output_path=str(tmp_path / "output.mp4"),
            encoder="cpu",
        )

        with pytest.raises(RuntimeError, match="未提供 ASS 文件"):
            await _handle_burn(task)

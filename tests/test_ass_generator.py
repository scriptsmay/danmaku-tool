"""ASS 生成器测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from danmaku_tool.core.ass_generator import (
    DanmakuAssGenerator,
    SegmentInfo,
)


class TestAssGenerator:
    """ASS 生成器核心测试。"""

    def test_format_ass_time(self):
        assert DanmakuAssGenerator._format_ass_time(0) == "0:00:00.00"
        assert DanmakuAssGenerator._format_ass_time(90.5) == "0:01:30.50"
        assert DanmakuAssGenerator._format_ass_time(3661.12) == "1:01:01.12"

    def test_calc_scroll_duration(self):
        gen = DanmakuAssGenerator()
        # 短文本
        d1 = gen._calc_scroll_duration(5)
        assert d1 == 12.0 + 5 * 0.15

        # 长文本应被 max 限制
        d2 = gen._calc_scroll_duration(200)
        assert d2 == 20.0

    def test_generate_header(self):
        gen = DanmakuAssGenerator()
        header = gen._generate_header(1920, 1080)
        assert "PlayResX: 1920" in header
        assert "PlayResY: 1080" in header
        assert "Noto Sans CJK SC" in header
        assert "[V4+ Styles]" in header

    def test_generate_header_720p(self):
        gen = DanmakuAssGenerator(font_size=36)
        header = gen._generate_header(1280, 720)
        # 字体应按比例缩小: 36 * 720/1080 = 24
        assert "24" in header

    def test_find_y_position(self):
        gen = DanmakuAssGenerator()
        # 空池，应返回 0
        y = gen._find_y_position(200, 1920, 1080, 36, 0.0, 12.0, [])
        assert y == 0

    def test_is_y_free_empty_pool(self):
        gen = DanmakuAssGenerator()
        assert gen._is_y_free(100, 200, 1920, 36, 0.0, 12.0, []) is True


class TestGenerateFromJsonl:
    """从 JSONL 生成 ASS 测试。"""

    @pytest.mark.asyncio
    async def test_generate_basic(self, sample_jsonl: Path, tmp_path: Path):
        gen = DanmakuAssGenerator()
        ass_path = str(tmp_path / "output.ass")

        result = await gen.generate_from_jsonl(
            jsonl_path=str(sample_jsonl),
            ass_path=ass_path,
            video_width=1920,
            video_height=1080,
        )

        assert result == ass_path
        assert Path(ass_path).exists()

        content = Path(ass_path).read_text(encoding="utf-8-sig")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Dialogue:" in content

    @pytest.mark.asyncio
    async def test_generate_empty_jsonl(self, tmp_path: Path):
        empty_jsonl = tmp_path / "empty.jsonl"
        empty_jsonl.write_text("", encoding="utf-8")

        gen = DanmakuAssGenerator()
        ass_path = str(tmp_path / "output.ass")

        await gen.generate_from_jsonl(
            jsonl_path=str(empty_jsonl),
            ass_path=ass_path,
        )

        assert Path(ass_path).exists()
        content = Path(ass_path).read_text(encoding="utf-8-sig")
        assert "[Script Info]" in content

    @pytest.mark.asyncio
    async def test_generate_nonexistent_jsonl(self, tmp_path: Path):
        gen = DanmakuAssGenerator()
        ass_path = str(tmp_path / "output.ass")

        await gen.generate_from_jsonl(
            jsonl_path="/nonexistent/path.jsonl",
            ass_path=ass_path,
        )
        # 应该生成空 ASS（不报错）
        assert Path(ass_path).exists()

    @pytest.mark.asyncio
    async def test_dedup_window(self, tmp_path: Path):
        """测试去重：5 秒窗口内的重复弹幕应被跳过。"""
        jsonl = tmp_path / "dedup.jsonl"
        lines = [
            '{"ts_ms":1000,"type":"comment","text":"重复","username":"u1"}',
            '{"ts_ms":2000,"type":"comment","text":"重复","username":"u2"}',
            '{"ts_ms":8000,"type":"comment","text":"重复","username":"u3"}',
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        gen = DanmakuAssGenerator()
        ass_path = str(tmp_path / "dedup.ass")
        await gen.generate_from_jsonl(str(jsonl), ass_path)

        content = Path(ass_path).read_text(encoding="utf-8-sig")
        dialogues = [line for line in content.split("\n") if line.startswith("Dialogue:")]
        # 第 1 条和第 3 条（间隔 > 5s）应保留，第 2 条应被去重
        assert len(dialogues) == 2


class TestGenerateSegmentAss:
    """分段 ASS 生成测试。"""

    @pytest.mark.asyncio
    async def test_segment_basic(self, sample_jsonl: Path, tmp_path: Path):
        gen = DanmakuAssGenerator()
        output_dir = str(tmp_path / "segments")

        segments = [
            SegmentInfo(recording_file_id=1, start_ms=0, end_ms=5000, output_path=""),
            SegmentInfo(recording_file_id=2, start_ms=5000, end_ms=25000, output_path=""),
        ]

        result = await gen.generate_segment_ass(
            jsonl_path=str(sample_jsonl),
            output_dir=output_dir,
            segments=segments,
        )

        assert len(result) == 2
        for path in result:
            assert Path(path).exists()
            content = Path(path).read_text(encoding="utf-8-sig")
            assert "Dialogue:" in content

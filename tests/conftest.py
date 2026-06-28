"""测试 fixtures。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from danmaku_tool.models.task import Task, TaskStatus, TaskType


@pytest.fixture(autouse=True)
def _setup_test_db(tmp_path: Path):
    """每个测试使用独立的临时数据库。"""
    import danmaku_tool.db.pool as pool_mod

    db_path = tmp_path / "test.db"
    pool_mod._db_path = db_path

    # 初始化 DB
    from danmaku_tool.db.pool import init_db
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init_db())
    loop.close()
    yield

    pool_mod._db_path = None


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """临时目录。"""
    return tmp_path


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    """创建样例 JSONL 文件。"""
    jsonl = tmp_path / "danmaku.jsonl"
    lines = [
        '{"ts_ms":1000,"type":"comment","text":"第一条弹幕","username":"user1"}',
        '{"ts_ms":2000,"type":"comment","text":"第二条弹幕","username":"user2"}',
        '{"ts_ms":3000,"type":"comment","text":"第三条弹幕","username":"user3"}',
        '{"ts_ms":5000,"type":"comment","text":"重复弹幕","username":"user4"}',
        '{"ts_ms":5500,"type":"comment","text":"重复弹幕","username":"user5"}',
        '{"ts_ms":10000,"type":"comment","text":"长弹幕测试这是一条比较长的弹幕内容用于测试滚动时长计算","username":"user6"}',
        '{"ts_ms":15000,"type":"gift","text":"礼物","username":"user7"}',
        '{"ts_ms":20000,"type":"comment","text":"最后一条弹幕","username":"user8"}',
    ]
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    return jsonl


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """创建假视频文件（仅用于路径测试，非真实视频）。"""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"\x00" * 1024)  # 1KB 假数据
    return video


@pytest.fixture
def sample_ass(tmp_path: Path) -> Path:
    """创建样例 ASS 文件。"""
    ass_file = tmp_path / "danmaku.ass"
    ass_content = """[Script Info]
Title: Test
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Noto Sans CJK SC,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,1,2,20,20,20,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:01.00,0:00:13.00,Default,,0,0,0,,{\\move(1920,100,-200,100)}测试弹幕
"""
    ass_file.write_text(ass_content, encoding="utf-8-sig")
    return ass_file


@pytest.fixture
def make_task():
    """创建任务的工厂函数。"""
    def _make(
        type: TaskType = TaskType.BURN,
        status: TaskStatus = TaskStatus.QUEUED,
        **kwargs,
    ) -> Task:
        return Task(type=type, status=status, **kwargs)
    return _make

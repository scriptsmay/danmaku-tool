"""ASS 字幕生成器。

从 JSONL 弹幕文件生成 Bilibili 风格滚动弹幕 ASS 字幕。
移植自 DanmakuAssGenerator.js，保持算法一致。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 匹配纯颜色代码，如 #9DCFFF、#fff、#FFF
_COLOR_CODE_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass
class DanmakuEvent:
    """弹幕事件。"""
    ts_ms: int          # 相对于录制开始的时间戳（ms）
    text: str           # 弹幕文本
    username: str = ""
    type: str = "comment"


@dataclass
class ActiveItem:
    """活跃弹幕（用于碰撞检测）。"""
    y: int
    text_width: int
    start_time: float   # 秒
    duration: float      # 滚动时长（秒）


@dataclass
class SegmentInfo:
    """分段信息。"""
    recording_file_id: int
    start_ms: int
    end_ms: int
    output_path: str


class DanmakuAssGenerator:
    """ASS 字幕生成器。

    核心算法：
    - 全局 active pool 碰撞调度（像素级 Y 轴扫描）
    - 动态滚动时长（12~20s，按文本长度）
    - 5 秒滑动窗口去重
    - 每秒最大 10 条密度限制
    """

    # ── 默认参数 ──
    DEFAULT_FONT_FAMILY = "Noto Sans CJK SC Medium"
    DEFAULT_FONT_SIZE = 36          # 1080p 基准
    DEFAULT_OPACITY = 0.88
    DEFAULT_OUTLINE_WIDTH = 1
    DEFAULT_MAX_PER_SECOND = 10
    DEFAULT_DEDUP_WINDOW_MS = 5000
    DEFAULT_BASE_DURATION = 12.0    # 基础滚动时长（秒）
    DEFAULT_EXTRA_PER_CHAR = 0.15   # 每多一个字符增加的时长
    DEFAULT_MAX_DURATION = 20.0
    DEFAULT_CHAR_WIDTH_RATIO = 0.6  # 字符宽度 ≈ font_size * ratio（CJK）
    VIDEO_WIDTH_REFERENCE = 1920

    def __init__(
        self,
        font_family: str = DEFAULT_FONT_FAMILY,
        font_size: int = DEFAULT_FONT_SIZE,
        opacity: float = DEFAULT_OPACITY,
        outline_width: int = DEFAULT_OUTLINE_WIDTH,
        max_per_second: int = DEFAULT_MAX_PER_SECOND,
    ):
        self.font_family = font_family
        self.font_size = font_size
        self.opacity = opacity
        self.outline_width = outline_width
        self.max_per_second = max_per_second

    async def generate_from_jsonl(
        self,
        jsonl_path: str,
        ass_path: str,
        video_width: int = 1920,
        video_height: int = 1080,
        offset_ms: int = 0,
    ) -> str:
        """从 JSONL 文件生成 ASS 字幕。

        Args:
            jsonl_path: JSONL 弹幕文件路径。
            ass_path: 输出 ASS 文件路径。
            video_width: 视频宽度。
            video_height: 视频高度。
            offset_ms: 时间偏移（ms）。

        Returns:
            输出 ASS 文件路径。
        """
        events = await self._load_jsonl(jsonl_path, offset_ms)
        if not events:
            logger.warning(f"JSONL 为空: {jsonl_path}")
            # 生成空 ASS
            ass_content = self._generate_header(video_width, video_height) + "\n[Events]\n"
        else:
            ass_content = self._generate_ass(events, video_width, video_height)

        Path(ass_path).parent.mkdir(parents=True, exist_ok=True)
        Path(ass_path).write_text(ass_content, encoding="utf-8-sig")
        logger.info(f"ASS 生成完成: {ass_path} ({len(events)} 条弹幕)")
        return ass_path

    async def generate_segment_ass(
        self,
        jsonl_path: str,
        output_dir: str,
        segments: list[SegmentInfo],
        video_width: int = 1920,
        video_height: int = 1080,
    ) -> list[str]:
        """为每个录制片段生成独立 ASS 文件。

        Args:
            jsonl_path: JSONL 弹幕文件路径。
            output_dir: 输出目录。
            segments: 片段信息列表。
            video_width: 视频宽度。
            video_height: 视频高度。

        Returns:
            生成的 ASS 文件路径列表。
        """
        events = await self._load_jsonl(jsonl_path)
        if not events:
            logger.warning(f"JSONL 为空: {jsonl_path}")
            return []

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        generated: list[str] = []

        for seg in segments:
            # 过滤属于该片段的弹幕（时间归一化到片段起始）
            seg_events = [
                DanmakuEvent(
                    ts_ms=e.ts_ms - seg.start_ms,
                    text=e.text,
                    username=e.username,
                    type=e.type,
                )
                for e in events
                if seg.start_ms <= e.ts_ms < seg.end_ms
            ]

            if not seg_events:
                logger.debug(f"片段 {seg.recording_file_id} 无弹幕，跳过")
                continue

            ass_content = self._generate_ass(seg_events, video_width, video_height)
            seg_ass_path = output_dir_path / f"{seg.recording_file_id}.ass"
            seg_ass_path.write_text(ass_content, encoding="utf-8-sig")
            generated.append(str(seg_ass_path))
            logger.info(f"分段 ASS: {seg_ass_path} ({len(seg_events)} 条)")

        return generated

    # ── 内部方法 ──

    async def _load_jsonl(self, jsonl_path: str, offset_ms: int = 0) -> list[DanmakuEvent]:
        """加载 JSONL 文件。"""
        events: list[DanmakuEvent] = []
        path = Path(jsonl_path)
        if not path.exists():
            logger.error(f"JSONL 文件不存在: {jsonl_path}")
            return events

        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        for line in content.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                event_type = data.get("type", "comment")
                if event_type not in ("comment", "gift", "like"):
                    continue
                # 只处理 comment 类型用于 ASS 渲染
                if event_type != "comment":
                    continue
                ts_ms = int(data.get("ts_ms", 0)) - offset_ms
                text = str(data.get("text", "")).strip()
                if not text:
                    continue
                # 过滤纯颜色代码弹幕
                if _COLOR_CODE_RE.match(text):
                    continue
                events.append(DanmakuEvent(
                    ts_ms=ts_ms,
                    text=text,
                    username=data.get("username", ""),
                    type=event_type,
                ))
            except (json.JSONDecodeError, ValueError):
                continue

        events.sort(key=lambda e: e.ts_ms)
        logger.info(f"加载 {len(events)} 条弹幕 from {jsonl_path}")
        return events

    def _generate_ass(
        self,
        events: list[DanmakuEvent],
        video_width: int,
        video_height: int,
    ) -> str:
        """生成完整 ASS 内容。"""
        header = self._generate_header(video_width, video_height)
        dialogues = self._generate_dialogues(events, video_width, video_height)
        return header + "\n[Events]\n" + "\n".join(dialogues) + "\n"

    def _generate_header(self, video_width: int, video_height: int) -> str:
        """生成 ASS Header。"""
        # 字体大小按视频高度缩放（1080p 基准）
        font_size = round(self.font_size * video_height / 1080)
        # 透明度转换：opacity 0.88 → ASS alpha &H1F（0=不透明, 255=全透明）
        alpha = round((1 - self.opacity) * 255)
        primary_colour = f"&H{alpha:02X}FFFFFF"
        outline_colour = "&H80000000"
        back_colour = "&H80000000"

        return f"""[Script Info]
Title: Danmaku
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{self.font_family},{font_size},{primary_colour},&H000000FF,{outline_colour},{back_colour},0,0,0,0,100,100,0,0,1,{self.outline_width},1,2,20,20,20,1"""

    def _generate_dialogues(
        self,
        events: list[DanmakuEvent],
        video_width: int,
        video_height: int,
    ) -> list[str]:
        """生成所有 Dialogue 行。"""
        font_size = round(self.font_size * video_height / 1080)
        char_width = round(font_size * self.DEFAULT_CHAR_WIDTH_RATIO)

        # 去重窗口
        dedup_window_ms = self.DEFAULT_DEDUP_WINDOW_MS
        recent_texts: dict[str, int] = {}  # text -> last_ts_ms

        # 密度限制
        per_second_count: dict[int, int] = {}  # second -> count

        # 活跃弹幕池（碰撞检测）
        active_pool: list[ActiveItem] = []

        dialogues: list[str] = []
        dropped_no_slot = 0

        for event in events:
            ts_sec = event.ts_ms / 1000.0
            second = event.ts_ms // 1000

            # 去重
            if event.text in recent_texts:
                if event.ts_ms - recent_texts[event.text] < dedup_window_ms:
                    continue
            recent_texts[event.text] = event.ts_ms

            # 密度限制
            count = per_second_count.get(second, 0)
            if count >= self.max_per_second:
                continue
            per_second_count[second] = count + 1

            # 计算滚动时长
            text_width = len(event.text) * char_width
            duration = self._calc_scroll_duration(len(event.text))

            # 碰撞调度：找 Y 位置
            y = self._find_y_position(
                text_width, video_width, video_height, font_size, ts_sec, duration, active_pool
            )
            if y is None:
                dropped_no_slot += 1
                continue

            # 加入活跃池
            active_pool.append(ActiveItem(
                y=y,
                text_width=text_width,
                start_time=ts_sec,
                duration=duration,
            ))

            # 清理过期弹幕
            active_pool = [
                item for item in active_pool
                if ts_sec - item.start_time < item.duration
            ]

            # 生成 Dialogue
            start_str = self._format_ass_time(ts_sec)
            end_str = self._format_ass_time(ts_sec + duration)
            # \move(x_start, y, x_end, y) — 从右侧滚到左侧
            effect = f"\\move({video_width},{y},{-text_width},{y})"
            dialogue = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{{effect}}}{event.text}"
            dialogues.append(dialogue)

        if dropped_no_slot:
            logger.warning(f"碰撞调度: 丢弃 {dropped_no_slot} 条弹幕（无空位）")

        return dialogues

    def _calc_scroll_duration(self, text_length: int) -> float:
        """计算滚动时长（秒）。"""
        duration = self.DEFAULT_BASE_DURATION + text_length * self.DEFAULT_EXTRA_PER_CHAR
        return min(duration, self.DEFAULT_MAX_DURATION)

    def _find_y_position(
        self,
        text_width: int,
        video_width: int,
        video_height: int,
        font_size: int,
        current_time: float,
        duration: float,
        active_pool: list[ActiveItem],
    ) -> int | None:
        """碰撞调度：扫描 Y 轴找到无重叠位置。

        返回 None 表示所有 Y 都被占用（含追击碰撞检查），该弹幕应被丢弃。
        """
        step = max(1, font_size // 4)
        max_y = video_height - font_size

        for y in range(0, max_y + 1, step):
            if self._is_y_free(y, text_width, video_width, font_size, current_time, duration, active_pool):
                return y

        return None

    def _is_y_free(
        self,
        y: int,
        text_width: int,
        video_width: int,
        font_size: int,
        current_time: float,
        duration: float,
        active_pool: list[ActiveItem],
    ) -> bool:
        """检查 Y 位置是否与活跃弹幕无重叠。

        新弹幕从右侧 (x=video_width) 进入，向左滚动。
        需要同时满足两项检查才认为无碰撞：
        1) 入场时旧弹幕的右边缘已离开屏幕右侧（入口让出）；
        2) 若新弹幕滚动更快（duration 更短），不会在屏幕内追上旧弹幕的尾巴。
        """
        for item in active_pool:
            if abs(item.y - y) >= font_size:
                continue
            elapsed = current_time - item.start_time
            if elapsed >= item.duration:
                continue  # 旧弹幕已滚完

            # 检查 1：入口让出（旧弹幕右边缘是否已离开 x=video_width）
            progress = elapsed / item.duration
            item_right = video_width - (video_width + item.text_width) * progress + item.text_width
            if item_right > 0:
                return False  # 挡住入口

            # 检查 2：追击碰撞（新弹幕更快时可能追上旧弹幕右边缘）
            if duration < item.duration:
                # 求解 new_left(t) == old_right(t)
                # new_left(t)  = video_width - (video_width + text_width) * (t - current_time) / duration
                # old_right(t) = video_width - (video_width + item.text_width) * (t - item.start_time) / item.duration
                # 得 t_cross - current_time = elapsed * duration / (item.duration - duration)
                dt_cross = elapsed * duration / (item.duration - duration)
                if dt_cross <= 0:
                    continue
                t_cross = current_time + dt_cross
                # 两者都还在屏幕上时才会碰撞
                if t_cross < current_time + duration and t_cross < item.start_time + item.duration:
                    return False

        return True

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        """秒数 → ASS 时间格式 H:MM:SS.cc。"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

"""后台 worker：取任务 → 执行 → 回调。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings
from ..core.ass_generator import DanmakuAssGenerator
from ..core.burner import DanmakuBurner, BurnProgress
from ..db import tasks_dao
from ..db.pool import get_db
from ..models.task import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


async def handle_task(task: Task) -> None:
    """处理单个任务。"""
    task.status = TaskStatus.PROCESSING
    task.started_at = datetime.now().isoformat()

    try:
        if task.type in (TaskType.BURN, TaskType.FREE_BURN):
            await _handle_burn(task)
        elif task.type == TaskType.ASS_GENERATE:
            await _handle_ass_generate(task)

        task.status = TaskStatus.COMPLETED
        task.progress = 100.0
        logger.info(f"任务完成: {task.id}")

    except asyncio.CancelledError:
        task.status = TaskStatus.CANCELLED
        raise

    except Exception as e:
        logger.exception(f"任务失败: {task.id}: {e}")
        task.status = TaskStatus.FAILED
        task.error = str(e)

    finally:
        task.completed_at = datetime.now().isoformat()
        async with get_db() as db:
            await tasks_dao.update(db, task)

        if task.callback_url:
            await _send_callback(task)


async def _handle_burn(task: Task) -> None:
    """执行压制任务。"""
    burner = DanmakuBurner(
        ffmpeg_path=settings.ffmpeg_path,
        ffprobe_path=settings.ffprobe_path,
    )

    # 如果是自由压制且有 JSONL，先生成 ASS
    ass_path = task.ass_path
    if task.type == TaskType.FREE_BURN and task.jsonl_path and not ass_path:
        generator = DanmakuAssGenerator()
        ass_path = str(Path(task.output_path).with_suffix(".ass"))
        await generator.generate_from_jsonl(
            jsonl_path=task.jsonl_path,
            ass_path=ass_path,
            video_width=task.video_width or 1920,
            video_height=task.video_height or 1080,
        )

    # 进度回调 → 更新 task 对象
    def on_progress(p: BurnProgress) -> None:
        task.progress = p.percent
        task.speed = p.speed

    result = await burner.burn(
        video_path=task.video_path,
        ass_path=ass_path,
        output_path=task.output_path,
        encoder=task.encoder,
        fps=task.fps,
        on_progress=on_progress,
    )

    if not result.success:
        raise RuntimeError(result.error)

    task.output_size = result.output_size
    task.output_path = result.output_path


async def _handle_ass_generate(task: Task) -> None:
    """执行 ASS 生成任务。"""
    generator = DanmakuAssGenerator()
    await generator.generate_from_jsonl(
        jsonl_path=task.jsonl_path,
        ass_path=task.output_path,
        video_width=task.video_width or 1920,
        video_height=task.video_height or 1080,
    )


async def _send_callback(task: Task) -> None:
    """发送 webhook 回调。"""
    payload = {
        "task_id": task.id,
        "status": task.status.value,
        "output_path": task.output_path,
        "output_size": task.output_size,
        "error": task.error,
        "metadata": json.loads(task.metadata) if task.metadata else None,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(task.callback_url, json=payload)
                if resp.status_code < 300:
                    logger.info(f"回调成功: task_id={task.id}")
                    return
                logger.warning(f"回调失败 (attempt {attempt+1}): HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"回调异常 (attempt {attempt+1}): {e}")

        await asyncio.sleep(2 ** attempt)

    logger.error(f"回调最终失败: task_id={task.id}")

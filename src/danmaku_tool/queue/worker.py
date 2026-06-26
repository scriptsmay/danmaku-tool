"""后台 worker：取任务 → 执行 → 回调。"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings
from ..core.ass_generator import DanmakuAssGenerator
from ..core.burner import BurnProgress, DanmakuBurner
from ..db import tasks_dao
from ..db.pool import get_db
from ..models.task import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


def _is_remote(path: str) -> bool:
    """判断路径是否为远程/网络路径（NFS、SMB 等）。"""
    p = Path(path)
    parts = p.parts
    if len(parts) >= 2 and parts[0] == "/" and parts[1] == "Volumes":
        return True  # macOS NFS/SMB 挂载
    if len(parts) >= 2 and parts[0] == "\\\\":
        return True  # Windows UNC 路径
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt":
        return True  # Linux 挂载
    return False


def _ensure_cache_dir(task_id: str) -> Path:
    """确保缓存目录存在，返回缓存目录路径。"""
    cache = settings.cache_dir / task_id
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _copy_to_cache(src: str, cache_dir: Path) -> str:
    """拷贝文件到本地缓存目录。"""
    src_path = Path(src)
    dst = cache_dir / src_path.name
    if src_path.resolve() == dst.resolve():
        return str(dst)
    logger.info(f"拷贝到缓存: {src} → {dst}")
    shutil.copy2(src, dst)
    return str(dst)


def _copy_from_cache(src: str, dst: str) -> None:
    """拷贝文件从缓存到目标路径。"""
    src_path = Path(src)
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"拷贝到目标: {src} → {dst}")
    shutil.copy2(src_path, dst_path)


def _cleanup_cache(cache_dir: Path) -> None:
    """清理缓存目录。"""
    try:
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            logger.info(f"清理缓存: {cache_dir}")
    except Exception as e:
        logger.warning(f"缓存清理失败: {e}")


async def handle_task(task: Task) -> None:
    """处理单个任务。"""
    task.status = TaskStatus.PROCESSING
    task.started_at = datetime.now().isoformat()

    try:
        if task.type in (TaskType.BURN, TaskType.FREE_BURN, TaskType.BURN_TEST):
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
        await _send_webhook(task)


async def _handle_burn(task: Task) -> None:
    """执行压制任务。支持本地缓存：远程文件先拷贝到本地，压制后再回传。"""
    burner = DanmakuBurner(
        ffmpeg_path=settings.ffmpeg_path,
        ffprobe_path=settings.ffprobe_path,
    )

    # 判断是否需要本地缓存
    use_cache = settings.cache_enabled and (
        _is_remote(task.video_path or "")
        or _is_remote(task.ass_path or "")
        or _is_remote(task.output_path or "")
    )

    cache_dir = _ensure_cache_dir(task.id) if use_cache else None
    original_output_path = task.output_path

    try:
        # JSONL → ASS 自动转换（适用于所有任务类型）
        ass_path = task.ass_path

        # ASS 输出目录：缓存目录 > 输出文件同级目录 > 输出目录
        ass_stem = Path(task.video_path).stem + ".ass"
        if use_cache:
            ass_dir = cache_dir
        elif task.output_path:
            ass_dir = Path(task.output_path).parent
        else:
            ass_dir = settings.danmaku_output_dir

        # 情况 1：自由压制有 jsonl_path 但没有 ass_path
        if task.type == TaskType.FREE_BURN and task.jsonl_path and not ass_path:
            generator = DanmakuAssGenerator()
            ass_path = str(ass_dir / ass_stem)
            await generator.generate_from_jsonl(
                jsonl_path=task.jsonl_path,
                ass_path=ass_path,
                video_width=task.video_width or 1920,
                video_height=task.video_height or 1080,
                offset_ms=task.offset_ms,
            )

        # 情况 2：任何任务选择了 .jsonl 文件作为弹幕文件
        elif ass_path and Path(ass_path).suffix.lower() == ".jsonl":
            generator = DanmakuAssGenerator()
            jsonl_path = ass_path
            ass_path = str(ass_dir / ass_stem)
            await generator.generate_from_jsonl(
                jsonl_path=jsonl_path,
                ass_path=ass_path,
                offset_ms=task.offset_ms,
            )

        # 拷贝输入文件到本地缓存
        if use_cache:
            logger.info(f"使用本地缓存: {cache_dir}")
            task.video_path = _copy_to_cache(task.video_path, cache_dir)
            ass_path = _copy_to_cache(ass_path, cache_dir)
            # 测试压制的输出路径已在本地（test_preview/），无需重定向
            if task.type != TaskType.BURN_TEST:
                task.output_path = str(cache_dir / Path(task.output_path).name)

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
            duration_limit=task.duration_limit,
            on_progress=on_progress,
        )

        if not result.success:
            raise RuntimeError(result.error)

        # 拷贝输出文件回远程目标
        if use_cache:
            _copy_from_cache(task.output_path, original_output_path)
            task.output_size = Path(original_output_path).stat().st_size
            task.output_path = original_output_path
        else:
            task.output_size = result.output_size
            task.output_path = result.output_path

    finally:
        if cache_dir:
            _cleanup_cache(cache_dir)


async def _handle_ass_generate(task: Task) -> None:
    """执行 ASS 生成任务。支持本地缓存。"""
    use_cache = settings.cache_enabled and _is_remote(task.jsonl_path or "")

    cache_dir = _ensure_cache_dir(task.id) if use_cache else None
    original_output_path = task.output_path

    try:
        jsonl_path = task.jsonl_path
        output_path = task.output_path

        if use_cache:
            logger.info(f"使用本地缓存: {cache_dir}")
            jsonl_path = _copy_to_cache(jsonl_path, cache_dir)
            output_path = str(cache_dir / Path(task.output_path).name)

        generator = DanmakuAssGenerator()
        await generator.generate_from_jsonl(
            jsonl_path=jsonl_path,
            ass_path=output_path,
            video_width=task.video_width or 1920,
            video_height=task.video_height or 1080,
        )

        if use_cache:
            _copy_from_cache(output_path, original_output_path)
            task.output_path = original_output_path

    finally:
        if cache_dir:
            _cleanup_cache(cache_dir)


async def _send_callback(task: Task) -> None:
    """发送 webhook 回调（per-task callback_url）。"""
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


async def _send_webhook(task: Task) -> None:
    """全局 webhook 通知（DANMAKU_WEBHOOK_ENABLED）。"""
    if not settings.webhook_enabled or not settings.webhook_callback_url:
        return

    event = "task.completed" if task.status == TaskStatus.COMPLETED else "task.failed"
    title = f"弹幕压制{'完成' if task.status == TaskStatus.COMPLETED else '失败'}"
    content = task.error or f"输出: {task.output_path} ({task.output_size or 0} bytes)"

    payload = {
        "event": event,
        "title": title,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "source": "danmaku-tool",
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(settings.webhook_callback_url, json=payload)
                if resp.status_code < 300:
                    logger.info(f"Webhook 通知成功: event={event}")
                    return
                logger.warning(f"Webhook 通知失败 (attempt {attempt+1}): HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Webhook 通知异常 (attempt {attempt+1}): {e}")

        await asyncio.sleep(2 ** attempt)

    logger.error(f"Webhook 通知最终失败: event={event}")

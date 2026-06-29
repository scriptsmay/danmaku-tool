"""danmaku-tool — FastAPI 应用入口。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import ass, burn, files, health, sessions, tasks
from .config import settings
from .db import tasks_dao
from .db.pool import get_db, init_db
from .deps import set_queue
from .queue.task_queue import TaskQueue
from .queue.worker import handle_task

# ── 日志配置 ──

def _setup_logging() -> None:
    """配置日志。"""
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.log_dir / "danmaku-tool.log", encoding="utf-8"),
        ],
    )

_setup_logging()
logger = logging.getLogger(__name__)

# ── Windows asyncio 异常抑制 ──

def _suppress_connection_reset() -> None:
    """抑制 Windows 上 asyncio 的 ConnectionResetError 噪音。"""
    if sys.platform != "win32":
        return
    loop = asyncio.get_event_loop()
    old_handler = loop.get_exception_handler()

    def _filtered_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return
        if old_handler:
            old_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_filtered_handler)


# ── 运行实例检查 ──

def _coerce_json_rows(raw: str) -> list[dict]:
    """Convert PowerShell ConvertTo-Json output to a list of objects."""
    if not raw.strip():
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _run_powershell_json(command: str) -> list[dict]:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        logger.debug("PowerShell 检查命令失败: %s", result.stderr.strip())
        return []
    try:
        return _coerce_json_rows(result.stdout)
    except json.JSONDecodeError as e:
        logger.debug("PowerShell JSON 解析失败: %s; output=%r", e, result.stdout[:500])
        return []


def _get_windows_port_listeners(port: int) -> list[dict]:
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"Get-NetTCPConnection -LocalPort {port} -State Listen | "
        "Select-Object LocalAddress,LocalPort,State,OwningProcess | "
        "ConvertTo-Json -Compress"
    )
    return _run_powershell_json(command)


def _get_windows_process_info(pids: set[int]) -> dict[int, dict]:
    if not pids:
        return {}
    pid_list = ",".join(str(pid) for pid in sorted(pids))
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$listenerPids=@({pid_list}); "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $listenerPids -contains $_.ProcessId } | "
        "Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    return {
        int(row["ProcessId"]): row
        for row in _run_powershell_json(command)
        if row.get("ProcessId") is not None
    }


async def _warn_duplicate_port_listeners(port: int) -> None:
    """Warn when another Windows process is also listening on the service port."""
    if sys.platform != "win32":
        return

    current_pid = os.getpid()
    listeners = await asyncio.to_thread(_get_windows_port_listeners, port)
    duplicate_listeners = [
        row
        for row in listeners
        if int(row.get("OwningProcess") or -1) != current_pid
    ]

    if not duplicate_listeners:
        logger.info("未发现其他进程监听端口 %s", port)
        return

    duplicate_pids = {int(row["OwningProcess"]) for row in duplicate_listeners if row.get("OwningProcess") is not None}
    process_info = await asyncio.to_thread(_get_windows_process_info, duplicate_pids)

    for row in duplicate_listeners:
        pid = int(row.get("OwningProcess") or -1)
        process = process_info.get(pid, {})
        logger.warning(
            "检测到其他进程也在监听端口 %s: address=%s pid=%s parent_pid=%s name=%s started=%s command=%s; "
            "如为遗留服务，请确认后结束该进程树，避免 localhost 与局域网 IP 命中不同实例。",
            port,
            row.get("LocalAddress"),
            pid,
            process.get("ParentProcessId", "unknown"),
            process.get("Name", "unknown"),
            process.get("CreationDate", "unknown"),
            process.get("CommandLine", "unknown"),
        )


# ── 模板和静态文件 ──

_templates_dir = Path(__file__).parent / "templates"
_static_dir = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(_templates_dir))

# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 DB 和 Worker。"""
    logger.info("danmaku-tool 启动中...")

    # 抑制 Windows asyncio ConnectionResetError 噪音
    _suppress_connection_reset()

    # 提示同端口重复服务实例，避免 localhost/LAN 命中不同进程
    await _warn_duplicate_port_listeners(settings.port)

    # 初始化数据库
    await init_db()

    # 初始化任务队列
    queue = TaskQueue(max_concurrent=settings.max_concurrent_tasks)
    set_queue(queue)

    # 恢复未完成任务
    async with get_db() as db:
        unfinished = await tasks_dao.list_unfinished(db)
        await queue.restore(unfinished)

    # 启动后台 worker
    worker_task = asyncio.create_task(queue.start_worker(handle_task))
    logger.info(f"Worker 已启动 (并发={settings.max_concurrent_tasks})")

    yield

    # 关闭
    queue.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("danmaku-tool 已停止")


# ── FastAPI App ──

app = FastAPI(
    title="danmaku-tool",
    description="弹幕压制工具 — ASS 字幕生成 + FFmpeg 视频压制",
    version="0.1.0",
    lifespan=lifespan,
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# 注册 API 路由
app.include_router(burn.router)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(ass.router)
app.include_router(health.router)
app.include_router(sessions.router)


# ── Web UI 页面路由 ──

@app.get("/favicon.ico")
async def favicon():
    """浏览器默认请求 /favicon.ico，重定向到静态文件。"""
    return RedirectResponse(url="/static/favicon.ico")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页：任务列表。"""
    return templates.TemplateResponse(name="index.html", request=request)


@app.get("/burn", response_class=HTMLResponse)
async def burn_page(request: Request):
    """新建压制任务页面。"""
    return templates.TemplateResponse(name="burn.html", request=request)


@app.get("/batch-burn", response_class=HTMLResponse)
async def batch_burn_page(request: Request):
    """批量压制页面。"""
    return templates.TemplateResponse(name="batch_burn.html", request=request)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """全局设置页面。"""
    return templates.TemplateResponse(name="settings.html", request=request)


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page(request: Request, task_id: str):
    """任务详情页面。"""
    return templates.TemplateResponse(name="task_detail.html", request=request, context={"task_id": task_id})


# ── CLI 入口 ──

def cli() -> None:
    """CLI 入口点。"""
    import argparse

    parser = argparse.ArgumentParser(description="danmaku-tool 弹幕压制工具")
    parser.add_argument("--host", default=settings.host, help="绑定地址")
    parser.add_argument("--port", type=int, default=settings.port, help="端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    uvicorn.run(
        "danmaku_tool.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    cli()

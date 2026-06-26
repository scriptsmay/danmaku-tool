"""danmaku-tool — FastAPI 应用入口。"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import ass, burn, files, health, tasks
from .config import settings
from .db.pool import init_db
from .deps import get_queue, set_queue
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
    old_handler = loop.call_exception_handler

    def _filtered_handler(context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return
        old_handler(context)

    loop.call_exception_handler = _filtered_handler

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

    # 初始化数据库
    await init_db()

    # 初始化任务队列
    queue = TaskQueue(max_concurrent=settings.max_concurrent_tasks)
    set_queue(queue)

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

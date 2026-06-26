# danmaku-tool

弹幕压制工具 — ASS 字幕生成 + FFmpeg 视频压制（NVENC/CPU）。

## 快速开始

### 1. 环境要求

- Python 3.12+
- uv
- FFmpeg 7.x+（需在 PATH 中，或在 `.env` 中指定路径）
- NVIDIA 驱动（使用 NVENC 时）

### 2. 安装

```bash
git clone <repo-url>
cd danmaku-tool

uv sync

cp .env.example .env
# 编辑 .env，修改 allowed_roots 和 danmaku_output_dir
```

### 3. 启动

```bash
# Windows
start.bat

# 或手动启动
uv run uvicorn danmaku_tool.main:app --host 127.0.0.1 --port 18000
```

打开浏览器访问 `http://localhost:18000`

## 使用方式

### Web UI（主要）

1. 打开 `http://localhost:18000`
2. 点击「新建压制任务」
3. 在文件浏览器中选择视频文件和弹幕文件（.jsonl 或 .ass）
4. 选择编码器（NVENC/CPU/自动），点击「自动填入」生成输出路径
5. 支持「压制测试」预览前 60 秒效果
6. 点击「开始压制」，任务详情页实时查看进度

### API 调用（自动化）

#### 单任务压制

```bash
curl -X POST http://localhost:18000/api/burn \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "D:\\Videos\\video.ts",
    "ass_path": "D:\\Videos\\video.ass",
    "encoder": "nvenc"
  }'
```

#### 会话批量压制（联动录制系统）

配置 `DANMAKU_SESSION_DIR` 后，传入 sessionId 自动查找分片视频和弹幕：

```bash
curl -X POST http://localhost:18000/api/burn/session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "26"}'
```

参数：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `session_id` | string | 是 | - | 录制会话 ID |
| `encoder` | string | 否 | `auto` | 编码器：`auto` / `nvenc` / `cpu` |
| `fps` | int | 否 | `30` | 输出帧率（24-60） |
| `callback_url` | string | 否 | null | 完成后回调 URL |
| `metadata` | object | 否 | null | 透传元数据 |

目录结构约定：

```
{session_dir}/{session_id}/
  ├── 20260625_225740.ts       ← 视频分片（自动排序）
  ├── 20260625_231500.ts
  └── danmaku/
      └── danmaku.jsonl        ← 弹幕数据
```

#### 其他 API

```bash
# 查看任务列表
curl http://localhost:18000/api/tasks

# 查看任务详情
curl http://localhost:18000/api/tasks/{task_id}

# 重试任务（失败→重入队，已完成→复制新任务）
curl -X POST http://localhost:18000/api/tasks/{task_id}/retry

# 删除任务记录
curl -X DELETE http://localhost:18000/api/tasks/{task_id}

# 健康检查 + 编码器能力
curl http://localhost:18000/api/health
```

## 配置说明

所有配置通过环境变量或 `.env` 文件设置，前缀 `DANMAKU_`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` / `PORT` | `127.0.0.1:18000` | 服务监听地址 |
| `FFMPEG_PATH` / `FFPROBE_PATH` | `ffmpeg` / `ffprobe` | FFmpeg 路径 |
| `DANMAKU_OUTPUT_DIR` | `C:\DanmakuOutput` | 默认输出目录 |
| `CACHE_ENABLED` | `true` | 远程文件本地缓存（NFS/SMB） |
| `CACHE_DIR` | `data/cache` | 缓存目录 |
| `MAX_CONCURRENT_TASKS` | `1` | 并发任务数（GPU 独占建议 1） |
| `ALLOWED_ROOTS` | - | 文件浏览器白名单目录 |
| `SESSION_DIR` | - | 会话批量压制目录 |
| `WEBHOOK_ENABLED` | `false` | 全局 Webhook 通知 |
| `WEBHOOK_CALLBACK_URL` | - | Webhook 回调地址 |
| `DB_PATH` | `data/danmaku_tool.db` | SQLite 数据库路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 功能特性

- **Web UI 操作** — 文件浏览器选文件、自动计算弹幕偏移、实时进度
- **NVENC GPU 加速** — RTX 3060 硬编码，libx264 作为 fallback
- **本地缓存** — 远程文件（NFS/SMB）自动拷贝到本地 SSD 压制后回传
- **任务持久化** — SQLite 存储，重启后自动恢复未完成任务
- **Webhook 通知** — 任务成功/失败时 POST 通知外部系统
- **会话批量压制** — 通过 sessionId 一键压制所有分片
- **失败重试** — 失败任务一键重试，已完成任务可复制新任务
- **压制测试** — 预览前 60 秒效果，浏览器内直接播放

## 项目结构

```text
danmaku-tool/
├── src/danmaku_tool/
│   ├── main.py              # FastAPI 入口 + 页面路由
│   ├── config.py            # 配置管理（pydantic-settings）
│   ├── deps.py              # 依赖注入
│   ├── api/
│   │   ├── burn.py          # 压制任务 API（单任务/批量/测试）
│   │   ├── tasks.py         # 任务查询 + SSE + 重试/删除
│   │   ├── files.py         # 文件浏览器 + 偏移量计算
│   │   ├── ass.py           # ASS 字幕生成 API
│   │   └── health.py        # 健康检查 + 编码器能力
│   ├── core/
│   │   ├── burner.py        # FFmpeg 压制引擎
│   │   ├── ass_generator.py # ASS 字幕生成（碰撞调度/去重/密度限制）
│   │   ├── capabilities.py  # FFmpeg 编码器探测
│   │   └── font_checker.py  # CJK 字体检测
│   ├── queue/
│   │   ├── task_queue.py    # asyncio 任务队列 + 持久化恢复
│   │   └── worker.py        # 后台 worker + Webhook 通知
│   ├── models/task.py       # Task 数据模型
│   ├── db/                  # SQLite 连接、迁移、DAO
│   ├── templates/           # Jinja2 模板
│   └── static/              # 前端 CSS/JS
├── tests/                   # pytest 测试用例
├── start.bat / stop.bat     # Windows 启停脚本
└── .env.example             # 配置模板
```

## 测试

```bash
uv run pytest
```

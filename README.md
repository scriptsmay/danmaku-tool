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
# 克隆项目
git clone <repo-url>
cd danmaku-tool

# 安装依赖
uv sync

# 复制配置文件
cp .env.example .env
# 编辑 .env，修改 allowed_roots 和 danmaku_output_dir
```

### 3. 启动

```bash
# Windows
start.bat

# 或手动启动
uv run uvicorn danmaku_tool.main:app --host 127.0.0.1 --port 8000
```

打开浏览器访问 http://localhost:8000

### 4. 使用

1. 点击「新建压制任务」
2. 在文件浏览器中选择视频文件（.mp4）和弹幕文件（.jsonl 或 .ass）
3. 选择编码器（NVENC/CPU/自动）
4. 点击「开始压制」
5. 在任务详情页查看实时进度

## 项目结构

```
danmaku-tool/
├── src/danmaku_tool/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── api/                 # API 路由
│   ├── core/                # 核心引擎（burner, ass_generator）
│   ├── queue/               # 任务队列
│   ├── models/              # 数据模型
│   ├── db/                  # 数据库（SQLite）
│   ├── templates/           # Jinja2 模板
│   └── static/              # 前端静态文件
├── tests/
├── start.bat / stop.bat     # Windows 启停脚本
└── .env.example             # 配置模板
```

## API 文档

启动后访问 http://localhost:8000/docs 查看 OpenAPI 文档。

### 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/burn` | 提交压制任务 |
| POST | `/api/burn/free` | 自由压制（跨会话） |
| POST | `/api/ass/generate` | 生成 ASS 字幕 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情 |
| GET | `/api/tasks/{id}/stream` | SSE 实时进度 |
| GET | `/api/files/browse` | 文件浏览器 |
| GET | `/api/health` | 健康检查 |

## 测试

```bash
uv run pytest
```

# /api/burn/session 修复开发文档

## 背景

`POST /api/burn/session` 用于按录制会话批量压制弹幕。接口接收 `session_id`，从 `DANMAKU_SESSION_DIR/{session_id}` 查找视频分片，并使用 `danmaku/danmaku.jsonl` 作为弹幕来源，为每个视频分片创建一个压制任务。

本次排查使用 session `28`，输入目录完整：

```text
Z:\videos\live_records\downloads\28\
  20260627_220247.ts
  20260627_230241.ts
  20260628_000240.ts
  20260628_010241.ts
  danmaku\danmaku.jsonl
```

接口能创建 4 个任务，但任务没有跑完整压制流程，全部失败。

## 已发现问题

### 1. localhost curl 被代理导致假性 502

在当前 PowerShell 环境中，`curl.exe` 会读取 `http_proxy`，连 `127.0.0.1:18000` 也会发往代理服务器，表现为：

```text
Uses proxy env variable http_proxy == 'http://192.168.31.247:7890'
HTTP/1.1 502 Bad Gateway
```

这不是 FastAPI 服务本身返回的错误，会干扰接口排查。

修复要求：

- README / AGENTS / 开发文档中的本地 curl 示例统一使用 `curl.exe --noproxy "*"`。
- Windows 启停或诊断脚本如果调用本地 HTTP，也应显式绕过代理。
- 排查文档中明确：先用 `curl.exe --noproxy "*"` 访问 `/api/health` 确认服务。

### 2. 运行中服务可能未加载最新源码

排查时发现服务进程启动时间早于本地最新提交，当前磁盘源码已经包含部分 JSONL 自动转 ASS 逻辑，但运行中的进程仍然按旧逻辑失败。

修复要求：

- 修改代码后必须重启服务再验证。
- `status.bat` 或文档中应提示检查进程启动时间。
- 最终验收时记录服务启动时间、当前 git commit、接口返回任务 ID。

### 3. session burn 创建 JSONL 任务后 worker 仍以空 ASS 路径压制

接口返回创建成功：

```json
{
  "session_id": "28",
  "video_count": 4,
  "task_ids": ["..."],
  "message": "已创建 4 个压制任务"
}
```

但所有任务失败：

```text
'NoneType' object has no attribute 'replace'
```

日志定位：

```text
src/danmaku_tool/core/burner.py:142
escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
```

任务详情显示：

```text
type        : burn
ass_path    :
jsonl_path  : Z:\videos\live_records\downloads\28\danmaku\danmaku.jsonl
error       : 'NoneType' object has no attribute 'replace'
```

核心问题：`/api/burn/session` 创建的是 `jsonl_path` 任务，`ass_path` 为空；worker 必须在调用 `DanmakuBurner.burn()` 前生成或解析出有效 ASS 文件路径。任何情况下都不能把 `None` 传给 `burner.burn(..., ass_path=...)`。

### 4. 缓存触发条件未覆盖映射盘路径

当前 `_is_remote()` 主要识别 UNC、`/Volumes`、`/mnt`。session 28 使用 `Z:\...` 映射盘路径，现有逻辑可能不会启用本地缓存。

影响：

- 大文件会直接从 NAS 映射盘读。
- 生成 ASS 可能写回视频同级目录。
- 压制速度和稳定性依赖映射盘 I/O。

修复要求：

- 明确是否把 Windows 映射盘视为远程输入。
- 如果启用缓存，需要同时缓存视频、生成后的 ASS，并将输出写入缓存后再复制到目标输出目录。
- 避免在没有必要时把大型 JSONL 或视频重复拷贝多次。

### 5. 批量任务输出文件名可能覆盖既有结果

默认输出路径是：

```text
D:\LiveCache\danmaku_output\{video_stem}_danmaku.mp4
```

重复提交同一 session 会创建新任务，但输出路径相同。可能覆盖已有成功产物，也会让重试结果难以区分。

修复要求：

- 明确重复提交策略：覆盖、跳过、失败、或生成唯一输出名。
- 若保留覆盖行为，API 响应和文档中需要说明。
- 推荐至少在任务创建前检测同名输出和同 session 活跃任务，避免误操作。

### 6. 任务 created_at 为空导致排序和审计弱

排查到 API 返回的任务 `created_at` 为空字符串。任务列表按 `created_at` 排序，空值会影响历史任务排序和排查。

修复要求：

- 创建 `Task` 时统一设置 `created_at=datetime.now().isoformat()`。
- 检查 `/api/burn`、`/api/burn/free`、`/api/burn/test`、`/api/burn/session` 和 retry 创建新任务路径。
- 补测试覆盖 API 创建任务的 `created_at` 非空。

### 7. API 创建成功不代表批量压制成功

`/api/burn/session` 当前只表示任务入队成功，不代表后续 ASS 生成、FFmpeg 压制和输出复制成功。排查时必须继续轮询任务详情。

修复要求：

- 文档和前端文案区分“已创建任务”和“压制完成”。
- 若前端有 session 批量入口，应展示每个 task 的状态、错误、输出路径和重试入口。
- API 可以保留异步语义，但响应中应包含足够的 task IDs 供调用方轮询。

## 修复范围

建议按以下文件切入：

| 文件 | 修改目标 |
|---|---|
| `src/danmaku_tool/api/burn.py` | session burn 创建任务时补齐时间戳，校验输入，明确输出冲突策略 |
| `src/danmaku_tool/queue/worker.py` | 保证 JSONL 转 ASS 后再调用 burner，缺少 ASS 时给出清晰错误 |
| `src/danmaku_tool/core/burner.py` | 对 `ass_path` 做防御式校验，避免 `NoneType.replace` |
| `src/danmaku_tool/queue/task_queue.py` | retry 复制任务时保留 output_path，并设置 created_at |
| `src/danmaku_tool/db/tasks_dao.py` | 如需要，完善时间字段和 output_path 更新策略 |
| `tests/` | 增加 session burn、JSONL 自动 ASS、created_at、retry/output_path 覆盖 |
| `README.md` / `AGENTS.md` | 更新本地 curl、验证步骤和异步任务语义 |

## 推荐实现方案

### A. 明确任务创建时间

新增一个小工具函数，或在每个 API 创建任务后设置：

```python
task.created_at = datetime.now().isoformat()
```

避免散落时可以考虑在 `Task` dataclass 的 `created_at` 使用 `default_factory`。

### B. Worker 中强制解析 ASS 输入

在 `_handle_burn()` 中形成单一入口：

```python
ass_path = await _resolve_ass_path(task)
if not ass_path:
    raise RuntimeError("未提供 ASS 文件，且无法从 JSONL 生成 ASS")
```

`_resolve_ass_path()` 负责：

- `task.ass_path` 是 `.ass`：直接返回。
- `task.ass_path` 是 `.jsonl`：生成同名 `.ass` 后返回。
- `task.jsonl_path` 存在且 `task.ass_path` 为空：生成同名 `.ass` 后返回。
- 两者都缺失：抛出清晰错误。

### C. Burner 做最后一道防线

`DanmakuBurner.burn()` 入参仍可保持 `str`，但开头增加：

```python
if not ass_path:
    return BurnResult(..., success=False, error="ASS 路径为空")
```

或直接 `raise ValueError("ASS 路径为空")`，由 worker 捕获为任务失败。错误信息必须可读，不能再出现 `NoneType.replace`。

### D. 缓存逻辑与 ASS 生成顺序

建议顺序：

1. 解析输入路径。
2. 如果 JSONL 需要生成 ASS，先生成 ASS。
3. 判断是否使用缓存。
4. 缓存视频和 ASS。
5. 将非测试任务输出重定向到缓存目录。
6. 调用 burner。
7. 成功后复制输出回目标路径。

需要特别验证映射盘 `Z:\` 和 UNC `\\server\share` 两类路径。

### E. 输出冲突策略

推荐第一阶段采用保守策略：

- 如果 output_path 已存在且任务不是显式 retry，生成唯一文件名，例如 `{stem}_danmaku_{task_id[:8]}.mp4`。
- API 响应和 task detail 返回最终 output_path。

如果产品上希望覆盖，则至少要在文档里说明重复提交会覆盖同名输出。

## 测试计划

### 单元 / 集成测试

- `POST /api/burn/session` 在临时 session 目录下发现多个视频和 `danmaku.jsonl`，返回 `video_count` 和 task IDs。
- session burn 创建的每个任务有：
  - `jsonl_path` 非空
  - `output_path` 非空
  - `created_at` 非空
- `_handle_burn()` 对 `jsonl_path` + 空 `ass_path` 的任务会调用 ASS 生成，并传入非空 `ass_path`。
- 缺少 `ass_path` 和 `jsonl_path` 时，任务失败错误为清晰中文/英文错误，不出现 `NoneType.replace`。
- retry 已完成任务时保留或重新生成合理 `output_path`，并设置新的 `created_at`。
- output_path 冲突策略有测试。

### 本地 smoke test

先确认服务已重启且健康：

```bash
curl.exe --noproxy "*" http://127.0.0.1:18000/api/health
```

提交 session burn：

```bash
curl.exe --noproxy "*" -X POST http://127.0.0.1:18000/api/burn/session -H "Content-Type: application/json" -d "{\"session_id\":\"28\"}"
```

轮询每个任务：

```bash
curl.exe --noproxy "*" http://127.0.0.1:18000/api/tasks/{task_id}
```

验收标准：

- 4 个任务全部不再出现 `NoneType.replace`。
- 每个任务先进入 `processing`，最终 `completed` 或给出明确可行动错误。
- 成功任务 `output_size > 0`。
- 输出文件实际存在。
- 日志中出现 ASS 生成完成和压制完成记录。

## 验收命令

```bash
uv run ruff check .
uv run pytest
curl.exe --noproxy "*" http://127.0.0.1:18000/api/health
curl.exe --noproxy "*" -X POST http://127.0.0.1:18000/api/burn/session -H "Content-Type: application/json" -d "{\"session_id\":\"28\"}"
```

## 非目标

- 不重构整个任务队列。
- 不改变 `/api/burn/session` 的异步入队语义。
- 不引入外部队列或数据库。
- 不处理 live-recorder-server 侧集成改造。

## 备注

本问题的关键不是单个 curl 命令失败，而是排查链路中同时存在代理干扰、服务未重启、JSONL→ASS 输入解析缺口、缓存策略不清晰、输出冲突和任务时间字段缺失。修复时应按完整链路验证，避免只修掉表面错误。

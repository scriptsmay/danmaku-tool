# Agent Instructions

danmaku-tool is a Python 3.12 + FastAPI service for danmaku ASS generation and FFmpeg hard-subtitle burning. It is usually run on Windows with NVIDIA NVENC, local SQLite persistence, and optional NAS-mounted recording inputs.

## Before You Start

```bash
git status --short --branch
uv sync
```

- The local worktree may contain user or agent commits ahead of `origin/main`; do not reset, rebase, or discard them unless explicitly requested.
- If a service is already running on port `18000`, check its process start time before testing. Restart it when validating code changes; otherwise it may still be serving old in-memory code.
- In PowerShell environments with proxy variables, use `curl.exe --noproxy "*"` for `localhost` / `127.0.0.1` requests.

## Common Commands

```bash
uv run pytest
uv run ruff check .
uv run mypy src
uv run python scripts/check_env.py
uv run uvicorn danmaku_tool.main:app --host 127.0.0.1 --port 18000
```

Windows helper scripts:

```bash
start.bat
status.bat
stop.bat
```

## Project Layout

| Area | Path |
|---|---|
| FastAPI app and routes | `src/danmaku_tool/main.py`, `src/danmaku_tool/api/` |
| Task model and persistence | `src/danmaku_tool/models/task.py`, `src/danmaku_tool/db/` |
| Queue and worker execution | `src/danmaku_tool/queue/` |
| FFmpeg burn engine | `src/danmaku_tool/core/burner.py` |
| JSONL to ASS generation | `src/danmaku_tool/core/ass_generator.py` |
| Frontend templates and static assets | `src/danmaku_tool/templates/`, `src/danmaku_tool/static/` |
| Tests | `tests/` |

## Development Rules

- Prefer small, focused changes that preserve the existing FastAPI + dataclass + DAO style.
- Keep API response shapes stable unless the user explicitly asks for a contract change.
- When adding fields to `Task`, update the dataclass, migration/schema handling, DAO insert/read/update paths, retry/copy logic, and API response models together.
- Do not hardcode machine-specific paths. Use `Settings` in `src/danmaku_tool/config.py` and `DANMAKU_` environment variables.
- Treat `.env`, `data/`, cache directories, logs, generated ASS files, and burned videos as local runtime artifacts. Do not commit secrets, SQLite DBs, logs, caches, or media outputs.
- Keep comments concise and useful; avoid restating obvious Python.

## FFmpeg And Danmaku Notes

- The burn path accepts either an existing ASS file or a JSONL file that must be converted to ASS before calling `DanmakuBurner.burn`.
- Never call `DanmakuBurner.burn()` with a missing `ass_path`; fail with a clear error or generate ASS first.
- Preserve Windows path escaping for FFmpeg filters and test with paths containing drive letters.
- For session batch burn, `POST /api/burn/session` expects:

```text
{DANMAKU_SESSION_DIR}/{session_id}/
  *.ts | *.mp4 | *.mkv | *.flv
  danmaku/danmaku.jsonl
```

- Session burn should create one task per video segment, using the shared session JSONL as input.
- Cache handling must copy all inputs needed by FFmpeg, including generated ASS files, and restore output paths after copying results back.

## Testing Guidance

- Run `uv run pytest` for normal changes.
- Run `uv run ruff check .` before finalizing Python edits.
- For API changes, include focused tests under `tests/test_api_*.py`.
- For worker or burn-flow changes, add tests around `Task`, `TaskQueue`, or `_handle_burn` behavior when possible.
- For real FFmpeg smoke tests, verify:

```bash
curl.exe --noproxy "*" http://127.0.0.1:18000/api/health
curl.exe --noproxy "*" -X POST http://127.0.0.1:18000/api/burn/session -H "Content-Type: application/json" -d "{\"session_id\":\"28\"}"
curl.exe --noproxy "*" http://127.0.0.1:18000/api/tasks
```

## Operational Checks

- Health endpoint: `GET /api/health`
- Task list: `GET /api/tasks`
- Task detail: `GET /api/tasks/{task_id}`
- Retry: `POST /api/tasks/{task_id}/retry`
- Delete: `DELETE /api/tasks/{task_id}`

When diagnosing failures, inspect `data/logs/danmaku-tool.log` first, then task records via the API. Prefer API-visible evidence in user reports: task IDs, status, output path, output size, and error string.

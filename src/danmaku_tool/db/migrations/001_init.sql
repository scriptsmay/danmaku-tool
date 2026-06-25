-- 001_init.sql — danmaku-tool 建表

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,                    -- UUID (hex)
    type TEXT NOT NULL,                     -- 'burn' | 'ass_generate' | 'free_burn'
    status TEXT NOT NULL DEFAULT 'queued',  -- 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'

    -- 输入参数
    video_path TEXT,
    ass_path TEXT,
    jsonl_path TEXT,
    output_path TEXT,
    encoder TEXT DEFAULT 'auto',            -- 'auto' | 'nvenc' | 'qsv' | 'cpu'
    fps INTEGER DEFAULT 30,
    video_width INTEGER,
    video_height INTEGER,

    -- 回调（可选）
    callback_url TEXT,
    metadata TEXT,                          -- JSON 字符串

    -- 结果
    progress REAL DEFAULT 0.0,              -- 0.0 ~ 100.0
    speed TEXT,                             -- FFmpeg speed，如 "3.2x"
    output_size INTEGER,                    -- 输出文件大小（bytes）
    error TEXT,

    -- 时间戳
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    name       TEXT PRIMARY KEY,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snippets (
    name       TEXT PRIMARY KEY,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    due_at     TEXT NOT NULL,
    text       TEXT NOT NULL,
    chat_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS download_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT NOT NULL,
    source     TEXT,
    created_at TEXT NOT NULL
);

-- Personal labels on Telegram users (CRM-lite)
CREATE TABLE IF NOT EXISTS tags (
    user_id      INTEGER NOT NULL,
    label        TEXT NOT NULL,
    note         TEXT,
    display_name TEXT,
    username     TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, label)
);

CREATE INDEX IF NOT EXISTS idx_tags_label ON tags(label);

-- DM keyword auto-replies
CREATE TABLE IF NOT EXISTS filters (
    keyword    TEXT PRIMARY KEY,
    response   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Locked user ids (auto-archive / ignore helpers)
CREATE TABLE IF NOT EXISTS locks (
    user_id      INTEGER PRIMARY KEY,
    display_name TEXT,
    username     TEXT,
    reason       TEXT,
    created_at   TEXT NOT NULL
);

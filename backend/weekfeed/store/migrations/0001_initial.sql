CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE projects (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
  label      TEXT NOT NULL CHECK (label IN ('work', 'school', 'personal')),
  created_at TEXT NOT NULL
);

CREATE TABLE repos (
  id               INTEGER PRIMARY KEY,
  project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  path             TEXT NOT NULL UNIQUE,
  display_name     TEXT NOT NULL,
  added_at         TEXT NOT NULL,
  last_fetched_at  TEXT,
  last_fetch_error TEXT
);

CREATE TABLE commits (
  id            INTEGER PRIMARY KEY,
  repo_id       INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  sha           TEXT NOT NULL,
  author_name   TEXT NOT NULL,
  author_email  TEXT NOT NULL,
  authored_at   TEXT NOT NULL,
  message       TEXT NOT NULL,
  files_changed TEXT NOT NULL,
  UNIQUE (repo_id, sha)
);
CREATE INDEX commits_repo_time ON commits(repo_id, authored_at);

CREATE TABLE items (
  id         INTEGER PRIMARY KEY,
  label      TEXT NOT NULL CHECK (label IN ('work', 'school', 'personal')),
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('note', 'todo', 'blocker')),
  text       TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (
    (kind = 'note' AND status = 'open') OR
    (kind = 'todo' AND status IN ('open', 'done')) OR
    (kind = 'blocker' AND status IN ('open', 'resolved'))
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at  TEXT
);
CREATE INDEX items_scope ON items(label, project_id, status);

CREATE TABLE drafts (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL CHECK (kind IN ('standup', 'weekly')),
  label        TEXT NOT NULL CHECK (label IN ('work', 'school', 'personal')),
  project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  period_start TEXT NOT NULL,
  period_end   TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('in_progress', 'saved')),
  sections     TEXT NOT NULL,
  record_text  TEXT,
  discord_text TEXT,
  created_at   TEXT NOT NULL,
  saved_at     TEXT
);
CREATE UNIQUE INDEX drafts_one_in_progress
  ON drafts(kind, label, IFNULL(project_id, 0)) WHERE status = 'in_progress';
CREATE INDEX drafts_scope ON drafts(kind, label, project_id, status, period_end);

CREATE TABLE agent_batches (
  id         INTEGER PRIMARY KEY,
  source     TEXT NOT NULL CHECK (source IN ('draft_chat', 'ask_chat')),
  label      TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  draft_id   INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
  input_text TEXT NOT NULL,
  summary    TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  undone_at  TEXT
);

-- item_kind / item_text snapshot the item so undone changes can still be shown.
CREATE TABLE batch_changes (
  id         INTEGER PRIMARY KEY,
  batch_id   INTEGER NOT NULL REFERENCES agent_batches(id) ON DELETE CASCADE,
  item_id    INTEGER NOT NULL,
  item_kind  TEXT NOT NULL,
  item_text  TEXT NOT NULL,
  action     TEXT NOT NULL CHECK (action IN ('created', 'status_changed')),
  old_status TEXT,
  new_status TEXT,
  applied_at TEXT NOT NULL
);

CREATE TABLE draft_messages (
  id             INTEGER PRIMARY KEY,
  draft_id       INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  role           TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content        TEXT NOT NULL,
  draft_snapshot TEXT,
  batch_id       INTEGER REFERENCES agent_batches(id) ON DELETE SET NULL,
  created_at     TEXT NOT NULL
);

CREATE VIRTUAL TABLE search_index USING fts5(
  content,
  source_type UNINDEXED,
  source_id UNINDEXED,
  tokenize = 'porter unicode61'
);

CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
  INSERT INTO search_index(content, source_type, source_id) VALUES (new.text, 'item', new.id);
END;
CREATE TRIGGER items_au AFTER UPDATE OF text ON items BEGIN
  DELETE FROM search_index WHERE source_type = 'item' AND source_id = old.id;
  INSERT INTO search_index(content, source_type, source_id) VALUES (new.text, 'item', new.id);
END;
CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
  DELETE FROM search_index WHERE source_type = 'item' AND source_id = old.id;
END;
CREATE TRIGGER commits_ai AFTER INSERT ON commits BEGIN
  INSERT INTO search_index(content, source_type, source_id)
  VALUES (new.message || char(10) || new.files_changed, 'commit', new.id);
END;
CREATE TRIGGER commits_ad AFTER DELETE ON commits BEGIN
  DELETE FROM search_index WHERE source_type = 'commit' AND source_id = old.id;
END;

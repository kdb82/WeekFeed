# WeekFeed design spec

- **Date:** 2026-10-07
- **Status:** draft, being written section by section
- **UI mockup:** https://claude.ai/artifact/3ydPGE9szXdq96Aay1mRwK

## 1. Overview

### Purpose
WeekFeed is a local web app for one person, Kaden (GitHub `kdb82`), running on their Mac. It turns the work they already record (git commits, quick notes, todos and blockers) into three things:

1. **Standups and weekly updates.** A standup is Yesterday / Today / Blockers. A weekly update is Done / Next / Blockers. Each can be scoped to one project or to a whole label (work, school, personal). Every draft is saved as a personal record and xVcan also be produced in a short Discord-ready format.
2. **A personal knowledge base.** A chat agent answers questions such as "how did I fix the auth bug?" from notes and commits across every label, citing its sources.
3. **Conversational item management.** While drafting, the user talks to an agent that adds notes, todos and blockers, closes them, and revises the draft. Every change can be undone.

### Success criteria
- Drafting a standup for any project or label takes one click plus optional chat, and the result is ready to paste.
- Work, school and personal content never mix in a draft.
- Only the user's own commits count.
- The knowledge-base agent answers from real sources with citations, and says so when it can't find an answer.
- Any change the agent makes can be undone.

### Non-goals
- WeekFeed never posts anything: not to Discord, GitHub or anywhere else. It only drafts text.
- One user, one machine. No accounts, no auth, no network exposure.
- No GitHub API. Commits are read from local clones, with a periodic `git fetch`.

### Deferred (possible later additions)
- A per-project switch to keep that project's data from being sent to OpenAI.
- Meaning-based search with embeddings. Search sits behind one function so it can be swapped in later.

## 2. Architecture

### Shape
```
Browser (React SPA)
   │  JSON over HTTP, 127.0.0.1 only
   ▼
FastAPI routes (thin)
   │
   ├── drafts ─┐
   ├── agent ──┼──► llm ──► OpenAI Responses API
   ├── search ─┘
   ├── sync ─────► git_reader ──► git (subprocess)
   │
   └── all of the above ──► store ──► SQLite (WAL, FTS5)
```

### Backend modules
The backend is a Python package, `backend/weekfeed/`. Each module has one job. Git, SQLite and OpenAI code each live in exactly one module, so any of them can be swapped by editing that module alone.

| Module | Job | Talks to |
|---|---|---|
| `config` | Loads `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL`, database path, port. | — |
| `git_reader` | The only code that runs git. Reads commits (`git log --all --no-merges`, with changed file names), runs `fetch` (10 s timeout, `GIT_TERMINAL_PROMPT=0`), validates repo paths, reads `user.email`/`user.name` from git config. | git |
| `store` | The only code that touches SQLite. Runs migrations (`PRAGMA user_version`) and provides typed functions for projects, repos, commits, items, drafts, messages, batches/undo, settings and FTS queries. Returns dataclasses, never raw rows. | SQLite |
| `llm` | The only code that talks to OpenAI. Exposes `respond(input, tools=None, output_schema=None) -> LLMResult` through a `Protocol`, so `FakeLLM` can stand in for it in tests. | OpenAI |
| `sync` | Brings a scope's repos up to date. Applies the 15-minute fetch throttle and a per-repo lock, then asks `git_reader` for commits newer than the latest stored one (minus one day of overlap; duplicates are ignored by the unique `(repo_id, sha)`) and hands them to `store`. | `git_reader`, `store` |
| `agent` | One shared tool-calling loop, at most 10 rounds per message. Each caller passes in a tool set: drafting chat gets the item tools plus `update_draft`, Ask chat gets `add_note` only. Enforces the label lock and records batches. | `llm`, `store` |
| `drafts` | Starts a draft session (works out the date range, syncs, gathers the context, generates v1), runs chat turns through `agent`, renders the Discord version, saves. | `sync`, `agent`, `llm`, `store` |
| `search` | Has the AI turn a question plus recent chat into keywords (falling back to stop-word removal), runs FTS5/BM25 for the top 15, then has the AI answer with `[n]` citations, using `agent` for the `add_note` tool. | `llm`, `store`, `agent` |
| `api` | FastAPI routers, which only parse, call a module and serialize. Also serves the built frontend. | the modules above |

Endpoints are plain `def`, not `async def`. FastAPI runs them in its threadpool, which works fine with blocking SQLite and `subprocess` calls at single-user scale.

### Frontend
`frontend/` is a Vite + React + TypeScript app.
- **Routes** (React Router):
  - `/`: the projects board, grouped by label
  - `/projects/:id`: history, the drafting chat, open items and Sync
  - `/labels/:label/draft`: the same drafting view, scoped to a whole label
  - `/ask`: knowledge-base chat
  - `/settings`: projects, repos, my emails, API key status
- **Data:** TanStack Query on top of a small typed API client (`src/api.ts`). Changes invalidate the queries they affect; for example, Sync refreshes the project cards.
- **Styles:** CSS modules, matching the mockup.

### Runtime
- **Daily use:** `npm run build` produces `frontend/dist/`, and FastAPI serves it next to `/api/*` on one URL bound to `127.0.0.1`.
- **Development:** the Vite dev server proxies `/api` to FastAPI.
- **Database:** one SQLite file, gitignored, at a path set in `.env` (default `./weekfeed.db`).

## 3. Data model

SQLite runs in WAL mode (`PRAGMA journal_mode = WAL`), so reads never block on a write. Each connection also sets `PRAGMA foreign_keys = ON` and `PRAGMA busy_timeout = 5000`, so a second writer waits instead of failing. The schema version lives in `PRAGMA user_version`, and numbered migrations run at startup.

**Timestamps** are stored as ISO-8601 UTC text. Anything that depends on the calendar ("previous workday", what counts as "today") is worked out in the Mac's local timezone.

### Tables

**`settings`**: a key/value store.
| column | type | notes |
|---|---|---|
| `key` | TEXT PK | |
| `value` | TEXT | JSON |

Keys:
- `my_emails`: a JSON array of lowercase author emails that count as "me."

**`projects`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE NOT NULL | |
| `label` | TEXT NOT NULL | `CHECK (label IN ('work','school','personal'))` |
| `created_at` | TEXT NOT NULL | |

**`repos`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `project_id` | INTEGER NOT NULL | FK → projects, `ON DELETE CASCADE` |
| `path` | TEXT UNIQUE NOT NULL | absolute, symlinks resolved |
| `display_name` | TEXT NOT NULL | defaults to the folder name |
| `added_at` | TEXT NOT NULL | |
| `last_fetched_at` | TEXT NULL | drives the 15-minute throttle |
| `last_fetch_error` | TEXT NULL | NULL when the last fetch worked; otherwise a short reason ("offline", "needs password", "folder missing") |

**`commits`**: every author's commits are stored; "mine" is filtered at query time.
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `repo_id` | INTEGER NOT NULL | FK → repos, `ON DELETE CASCADE` |
| `sha` | TEXT NOT NULL | `UNIQUE (repo_id, sha)` |
| `author_name` | TEXT NOT NULL | |
| `author_email` | TEXT NOT NULL | lowercased |
| `authored_at` | TEXT NOT NULL | the **author** date, i.e. when the work was done; it doesn't change on rebase |
| `message` | TEXT NOT NULL | the full message |
| `files_changed` | TEXT NOT NULL | newline-separated paths |

- **Index:** `(repo_id, authored_at)`.
- **Same commit in two repos** (for example, a fork and its upstream are both registered): drafts dedupe by `sha`.

**`items`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `label` | TEXT NOT NULL | same CHECK as `projects.label` |
| `project_id` | INTEGER NULL | FK → projects, `ON DELETE SET NULL` |
| `kind` | TEXT NOT NULL | `note` \| `todo` \| `blocker` |
| `text` | TEXT NOT NULL | any length |
| `status` | TEXT NOT NULL | a note is always `open`; a todo is `open` \| `done`; a blocker is `open` \| `resolved`. This is enforced by a CHECK on `(kind, status)`. |
| `created_at`, `updated_at` | TEXT NOT NULL | `updated_at` changes on every write |
| `closed_at` | TEXT NULL | set when a todo is done or a blocker resolved |

- **Index:** `(label, project_id, status)`.
- **Relabeling a project** updates the `label` of that project's items in the same transaction.

**`drafts`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `kind` | TEXT NOT NULL | `standup` \| `weekly` |
| `label` | TEXT NOT NULL | the scope's label |
| `project_id` | INTEGER NULL | NULL means a label-wide draft. FK → projects, `ON DELETE CASCADE` |
| `period_start`, `period_end` | TEXT NOT NULL | fixed when the session starts; "Change range" edits them and regenerates |
| `status` | TEXT NOT NULL | `in_progress` \| `saved` |
| `sections` | TEXT NOT NULL | JSON `[{"title": "Yesterday", "text": "..."}, ...]`, the working copy |
| `record_text` | TEXT NULL | rendered from `sections` on save |
| `discord_text` | TEXT NULL | the cached Discord version, cleared whenever `sections` changes |
| `created_at` | TEXT NOT NULL | |
| `saved_at` | TEXT NULL | |

- **Uniqueness:** a partial unique index on `(kind, label, IFNULL(project_id, 0)) WHERE status = 'in_progress'` allows at most one in-progress standup and one in-progress weekly update per scope.
- **Next draft's range:** it starts at the `period_end` of the latest **saved** draft with the same kind and scope. Using `period_end` rather than `saved_at` means no gap and no overlap.

**`draft_messages`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `draft_id` | INTEGER NOT NULL | FK → drafts, `ON DELETE CASCADE` |
| `role` | TEXT NOT NULL | `user` \| `assistant` |
| `content` | TEXT NOT NULL | |
| `draft_snapshot` | TEXT NULL | JSON copy of `sections` after this turn (shown as "Draft v1 / v2") |
| `batch_id` | INTEGER NULL | FK → agent_batches; set on the assistant message whose turn changed items |
| `created_at` | TEXT NOT NULL | |

**`agent_batches`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `source` | TEXT NOT NULL | `draft_chat` \| `ask_chat` |
| `label` | TEXT NULL | the label lock. NULL is used only for Ask chat, whose `add_note` takes an explicit label. |
| `project_id` | INTEGER NULL | |
| `draft_id` | INTEGER NULL | FK → drafts, `ON DELETE SET NULL` |
| `input_text` | TEXT NOT NULL | the user message that caused the batch. It's needed because Ask chats aren't stored. |
| `summary` | TEXT NOT NULL | |
| `created_at` | TEXT NOT NULL | |
| `undone_at` | TEXT NULL | |

**`batch_changes`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `batch_id` | INTEGER NOT NULL | FK → agent_batches, `ON DELETE CASCADE` |
| `item_id` | INTEGER NOT NULL | No FK, so a hand-deleted item doesn't break the batch history. Undo reports it as "already gone." |
| `action` | TEXT NOT NULL | `created` \| `status_changed` |
| `old_status`, `new_status` | TEXT NULL | |
| `applied_at` | TEXT NOT NULL | Undo's conflict check is `items.updated_at > applied_at` |

### Search index
```sql
CREATE VIRTUAL TABLE search_index USING fts5(
  content,
  source_type UNINDEXED,   -- 'item' | 'commit'
  source_id   UNINDEXED,
  tokenize = 'porter unicode61'
);
```
- **Content:**
  - An item's row holds its `text`.
  - A commit's row holds `message` plus `files_changed`. The `unicode61` tokenizer splits `auth/session.py` into `auth`, `session` and `py`.
- **Stemming:** `porter` makes `fix`, `fixed` and `fixing` match.
- **Triggers** on `items` (insert, update, delete) and `commits` (insert, delete) keep the index in sync.
- **Label, project and author aren't stored in the index.** Search joins back to `items` or `commits → repos → projects` for citations and for the "only my commits" filter (`author_email IN my_emails`). So relabeling a project or editing `my_emails` takes effect immediately, with no reindexing.

### Deleting things
- **Removing a repo** deletes its commits, and the triggers remove their index rows.
- **Deleting a project:** the user must type the project's name to confirm.
  - Its repos, commits and drafts (with their chats) are deleted.
  - Its **items are kept** as label-only items (`project_id → NULL`), so notes stay in the knowledge base.

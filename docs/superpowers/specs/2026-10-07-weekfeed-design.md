# WeekFeed design spec

- **Date:** 2026-10-07
- **Status:** complete draft, in review
- **UI mockup:** https://claude.ai/artifact/3ydPGE9szXdq96Aay1mRwK

## 1. Overview

### Purpose
WeekFeed is a local web app for one person (the author, GitHub `kdb82`), running on their Mac. It turns the work they already record (git commits, quick notes, todos and blockers) into three things:

1. **Standups and weekly updates.** A standup is Yesterday / Today / Blockers. A weekly update is Done / Next / Blockers. Each can be scoped to one project or to a whole label (work, school, personal). Every draft is saved as a personal record and can also be produced in a short Discord-ready format.
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
The backend is a Python package, `backend/src/weekfeed/` (src layout). Each module has one job. Git, SQLite and OpenAI code each live in exactly one module, so any of them can be swapped by editing that module alone.

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
- `github_username`: a string such as `"kdb82"`, used only to suggest candidate emails (§4.2).

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
| `draft_before`, `draft_after` | TEXT NULL | Drafting chat only: the draft's sections (JSON) just before and after the turn, so Undo can restore the text (§4.5). |

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

## 4. Flows

### 4.1 Sync
`sync.sync_repos(repos, force)` runs the following for each repo:

1. **Lock.** Take that repo's lock. If a sync of the repo is already running, wait for it to finish and reuse its result.
2. **Check the folder.** If the path no longer exists, set `last_fetch_error = "folder missing"` and skip the repo.
3. **Fetch** when `force` is set or `last_fetched_at` is 15+ minutes old: run `git_reader.fetch`.
   - On success, set `last_fetched_at` and clear `last_fetch_error`.
   - On failure, store the short reason and keep going. Reading local commits still works.
4. **Read commits.** Call `git_reader.read_commits(path, since)`:
   - `since` is the latest stored `authored_at` for this repo minus one day, or no limit if nothing is stored yet.
   - The read uses `git log --all --no-merges` with a machine-readable `--format` and `--name-only`.
   - New rows are inserted, and existing `(repo_id, sha)` pairs are ignored.

**When sync runs:**
| Trigger | Scope | `force` |
|---|---|---|
| Sync button (project page) | that project's repos | yes |
| Sync all (home page) | every repo | yes |
| Starting a draft session | the draft's scope | no |
| Opening the Ask page | every repo, in the background | no |
| Adding a repo | that repo (full history) | yes |

### 4.2 "My emails" detection
- **When:** after a repo is added, and when the user clicks Rescan.
- **What's shown:** Settings lists each distinct `author_email` in `commits`, with its commit count.
- **Candidates for "me":**
  - `git config --global user.email`
  - each registered repo's local `user.email`
  - any email matching `<github_username>@users.noreply.github.com` or `<digits>+<github_username>@users.noreply.github.com`
  - any email whose commits have `author_name` equal to `github_username` (case-insensitive)
- **Checking:**
  - While `my_emails` is empty (first setup), candidates are pre-checked.
  - After that, the saved list is authoritative. A newly found candidate shows a "new · looks like you" chip but stays unchecked until the user saves.
- `github_username` is a `settings` key, edited on the Settings page. It's blank until set, and while it's blank only the git-config candidates apply.

### 4.3 Drafting session

**Start** (New standup / New weekly update / "Standup for all ‹label›"):
1. **Reuse or create.** If an in-progress draft of this kind and scope exists, open it. Otherwise create one with this range:
   - **start:** the latest saved draft's `period_end` for the same kind and scope. With none, a standup uses the previous workday at 00:00 local time (Friday if today is Monday), and a weekly update uses now minus 7 days.
   - **end:** now.
2. **Sync** the scope (not forced).
3. **Gather the context** for the range:
   - **My commits:** `author_email ∈ my_emails`, deduplicated by `sha`, newest first, capped at 200. Each one carries its project, message and changed files.
   - todos closed and blockers resolved in the range
   - notes created in the range
   - all **open** todos and blockers in scope
   - Label-wide drafts group everything by project. Items without a project go under "General."
4. **Generate v1.** One `llm.respond` call with a structured output schema: `sections: [{title, text}]`, with titles fixed per kind (Yesterday/Today/Blockers or Done/Next/Blockers). The prompt says to include every open todo in Today/Next and every open blocker in Blockers, or write "None." Store the result as `drafts.sections` along with an assistant message carrying `draft_snapshot`.

**Chat turn** (the user sends a message):
1. Save the user message.
2. Build the agent input:
   - the system rules
   - the gathered context, re-gathered so it reflects the current open items
   - the current `sections`, including any manual edits
   - prior messages, as text
   
   The full input is sent on every turn. The app doesn't rely on OpenAI's server-side conversation state, so history stays in SQLite and `FakeLLM` behaves identically.
3. Run `agent.run_turn` with the drafting tool set (4.4).
4. **If items changed but the model never called `update_draft`,** the server adds one more round with a nudge ("items changed; call update_draft"). That round counts toward the 10-round cap.
5. Save the assistant message with its `draft_snapshot` and the `batch_id` if items changed. Return it.

**Manual edits:** the section textareas autosave (debounced `PATCH /api/drafts/{id}`). Every change to `sections` clears `discord_text`. The next agent turn starts from the edited text.

**Discord tab:**
1. Return `discord_text` if it's cached.
2. Otherwise make one `llm.respond` call that turns the current sections into bold headers + `- ` bullets, titled `**Standup · Wed Oct 7 · api-server**` (weekly: `**Weekly · Sep 30 – Oct 7 · work**`).
3. If the result is over 2,000 characters, make one "shorten" call.
4. If it's still over, return it with `over_limit: true` so the UI can show the counter in red.

**Change range:** update `period_start`/`period_end`, regenerate v1 (this replaces `sections`), and add an assistant message saying the range changed. Earlier messages stay.

**Save:**
1. Render `record_text` from `sections` (each title on its own line, then the section text, with a blank line between sections).
2. Make sure `discord_text` exists, generating it if needed.
3. Set `status = saved` and `saved_at`.

A saved draft is read-only in history.

**Discard** (in-progress only): deletes the draft and its messages. Item changes made during the chat stay; each batch can still be undone from its record.

### 4.4 Agent turn (`agent.run_turn`)
**Inputs:**
- the scope: `label`, and optionally `project_id`
- the tool set
- the input messages
- the source: `draft_chat` or `ask_chat`
- `draft_id`, if any

**Loop:** call `llm.respond` with the tools.
- **Tool calls:** run each through `store`, then send the results back.
- **Plain message:** the loop ends.
- **Round 10 reached:** the loop stops, and the message says it stopped early.

**Drafting tool set:**
| Tool | Args | Effect |
|---|---|---|
| `list_open_items` | `project?` | open todos and blockers in scope, with ids |
| `add_note` / `add_todo` / `add_blocker` | `text`, `project?` | creates an item |
| `mark_todo_done` | `item_id` | status `open → done` |
| `resolve_blocker` | `item_id` | status `open → resolved` |
| `update_draft` | `sections: [{title, text}]` | replaces `drafts.sections`; titles must match the kind |

**Ask tool set:** only `add_note(text, label, project?)`. Its label is required, because Ask spans every label.

**Rules enforced in code** (each violation goes back to the model as a tool error, never an exception):
- **Label lock:**
  - An `item_id` outside the batch's label is reported as "not found."
  - `project` is a project **name**, matched case-insensitively within the label. An unknown name returns the list of valid names.
  - In a project-scoped run, a missing `project` defaults to the scope's project.
- **Valid transitions:**
  - `mark_todo_done` works only on an open todo.
  - `resolve_blocker` works only on an open blocker.
- **Batches:**
  - The batch is created on the turn's first write, so read-only turns create no batch.
  - Each write and its `batch_changes` row share one transaction.
  - The batch `summary` is the final assistant text (first 200 characters).

**Prompt rule (not enforced in code):** when it's unclear which item the user means, change nothing for that part, and ask.

### 4.5 Undo
`POST /api/batches/{id}/undo` with an optional `force`:
1. **Load and check.** Load the batch's changes. If any changed item has `updated_at > applied_at`, and `force` isn't set, return `409` with the list ("'Review Sam's PR' was edited after this batch"). The UI shows that list and offers **Undo anyway**, which resends with `force`.
2. **Revert, newest-first, in one transaction:**
   - `created`: delete the item.
   - `status_changed`: restore `old_status` and set `closed_at` to match.
   - An item that no longer exists is skipped and reported as "already gone."
3. **Restore the draft text** (same transaction; drafting-chat batches only). If the draft is still in progress and its sections still equal `draft_after`, set them back to `draft_before` and clear the cached Discord version. If the draft changed since that turn (a later turn or a hand edit), leave the text alone so no later work is lost. The response's `draft_restored` is `true`, `false` (the UI then says the text wasn't reverted) or `null` (no draft involved).
4. **Finish.** Set `undone_at`. A batch can be undone only once.

### 4.6 Ask chat
`POST /api/ask` takes `{messages: [{role, content}, ...]}`. The client holds the whole conversation and the server stores none of it.

1. **Keywords:** an `llm.respond` call with a structured schema `{terms: [string]}`. Its input is the latest question plus the previous two turns, so follow-ups resolve.
2. **Search:**
   - Build the FTS query: each term quoted and joined with `OR`.
   - Filter: items from every label; commits only where `author_email ∈ my_emails`.
   - Rank by `bm25` and take the top 15.
   - **Zero hits or a failed keyword call:** retry with the latest question minus stop words.
3. **Answer:** `agent.run_turn` with the Ask tool set. The input includes the numbered sources and the conversation, with these rules:
   - answer only from the sources
   - cite them as `[n]`
   - if the answer isn't there, say "I couldn't find this in your notes or commits"
4. **Return** `{answer, citations: [{n, source_type, source_id, title, meta, body}], batch_id?}`. Citation numbers restart with each answer.
5. **"Save answer as note"** calls the same `add_note` path from the UI. The label and project come from a small picker, defaulting to the most-cited source's.

### 4.7 Settings flows
**Add project:** name + label.

**Rename:** in place.

**Relabel:** in one transaction, the project's items take the new label. Saved drafts keep the label they were written under.

**Add repo:**
1. The path must exist and be a git work tree (`git rev-parse --is-inside-work-tree`).
2. Resolve it to an absolute path with symlinks resolved, then insert. A duplicate path is rejected.
3. Run a full sync, then detection (4.2).

**Remove repo:** delete it; its commits and their index rows cascade.

**Delete project:** confirmed by typing its name. Deletion runs as described in §3, "Deleting things."

## 5. UI

There are three pages, matching the mockup, plus the label-wide drafting view, which reuses the project page's layout.

### 5.1 Global
- **Top nav:** Projects · Ask · Settings.
- **Banners** (persistent, dismissible per session):
  - "AI features are off: add `OPENAI_API_KEY` to `.env`"
  - "Confirm your commit emails in Settings", shown while `my_emails` is empty
- **Toasts** report failed actions.
- **No streaming in v1.** AI calls show a pending state ("Drafting…", "Thinking…"). The composer and the draft's buttons are disabled until the call returns.

### 5.2 Projects board (`/`)
- **Header:** the "Projects" title, the last sync time and a **Sync all** button.
- **Columns:** one per label, always in the order Work, School, Personal, each with its own tint.
- **Column header:** the label pill, the project count, and a **Standup for all ‹label›** link to `/labels/:label/draft`.
- **Project card** (the whole card links to `/projects/:id`). It shows:
  - the name
  - repo display names
  - chips for open todos, open blockers (red) and any repo with a `last_fetch_error` (amber)
  - the last saved standup date, or "No standups yet"
  - the time of the oldest fetch among its repos
- **"+ New project"** at the bottom of each column opens an inline name field. The label comes from the column.
- **Empty state** (no projects): a short explainer and the inline create field.

### 5.3 Drafting view (`/projects/:id` and `/labels/:label/draft`)
A single `DraftWorkspace` component serves both routes; only its scope prop differs.

**Header**
- Breadcrumb, name, label pill, repo paths, one sync chip per repo, and **Sync**.
- On the label view, Sync covers every repo in the label.

**Left column**
- Buttons: **New standup** and **New weekly update**.
- **History**, in this order:
  - in-progress drafts first, marked "in progress"
  - then saved drafts, newest first, each showing its kind and date
- **Default selection:** the in-progress draft if there is one, otherwise the latest saved draft, otherwise an empty state with a "Start a standup" button.

**Center, for an in-progress draft**
- **Range bar** at the top: "Tue Oct 6, 9:12am → Wed Oct 7, 9:05am · 5 commits · 1 todo done · 1 note", plus a **Change range** popover with two datetime inputs.
- **Thread:**
  - Your messages appear as right-aligned bubbles.
  - Assistant messages show:
    - their text
    - **change chips** for any batch, such as "added todo" or "resolved", with **Undo**. After an undo, the chips are struck through and marked "Undone."
    - Earlier draft snapshots collapse to "Draft vN · replaced".
- **Draft card** below the thread: the latest version, always expanded.
  - It has **Record** and **Discord** tabs.
  - Record shows one autosaving textarea per section.
  - Discord shows the formatted text plus a character counter, which turns red over 2,000.
  - Actions: **Copy** (copies the active tab), **Save standup** and a ⋯ menu with **Discard**.
- **Composer** pinned at the bottom: Enter sends and Shift+Enter adds a newline.
- **Undo conflicts** open a dialog listing the conflicting items, with **Undo anyway** and **Cancel**.

**Center, for a saved draft:** the Record and Discord versions side by side, read-only, each with **Copy**. The header shows the range and the save time.

**Right panel** (read-only): open **Todos**, open **Blockers** and the 5 most recent **Notes** in scope, with the hint "Change these by telling the agent." It refreshes after every chat turn and every undo.

### 5.4 Ask (`/ask`)
- **Layout:** a centered thread up to 820px wide, the composer at the bottom, and **New chat** in the header (it asks first if the thread isn't empty).
- **Assistant answers** include:
  - a muted "searched: term · term… → N matches" line
  - the answer text, with inline `[n]` badges
  - a row of **source chips** (`note · api-server · Oct 7`, `commit a1b2c3d`). Clicking a chip opens a card with the full text and its label, project and date.
  - **Save answer as note**, which opens a label/project picker
  - Notes the agent adds appear as change chips with Undo.
- **State:** the thread lives only in React state. A page reload clears it.

### 5.5 Settings (`/settings`)
- **Projects:**
  - list each project with its label pill and repo count
  - Rename and Change label act inline
  - Delete uses a type-the-name confirmation
  - an add form takes a name and a label
- **Repos:**
  - list each repo with its path, project and fetch status
  - each repo can be removed
  - an add form takes a path and a project; validation errors show inline
- **My commit emails:**
  - a `github_username` field
  - a checklist of every author email with its commit count, a reason chip ("your git config", "GitHub private email", "author name matches") and a "new" chip where it applies
  - **Rescan** and **Save** buttons
- **AI** (read-only): API key status (loaded or missing) and the model name. A hint explains these come from `.env`.

### 5.6 Frontend structure
```
frontend/src/
  api.ts            typed fetch wrappers, one per endpoint
  types.ts          response types mirroring the backend's Pydantic models
  pages/            ProjectsPage, DraftWorkspacePage, AskPage, SettingsPage
  components/       DraftCard, ChatThread, Composer, ChangeChips, UndoButton,
                    SourceChips, LabelPill, SyncChips, ConfirmDialog, Toasts
```
- **Queries:** TanStack Query keys follow resources: `['projects']`, `['drafts', scope]`, `['draft', id]`, `['items', scope]`, `['settings']`.
- **Invalidation:** each mutation invalidates the keys it affects. For example, a chat turn invalidates `['draft', id]` and `['items', scope]`.

### 5.7 API endpoints
All endpoints live under `/api` and speak JSON. Request and response bodies are Pydantic models.

| Method + path | Purpose |
|---|---|
| `GET /health` | `{api_key_loaded, model, git_available}` |
| `GET /projects` | projects with card stats |
| `POST /projects` · `PATCH /projects/{id}` · `DELETE /projects/{id}` | create; rename or relabel; delete (body: `{confirm_name}`) |
| `POST /repos` · `DELETE /repos/{id}` | add (validates, then a full sync and detection); remove |
| `POST /sync` | body `{project_id?, label?, force = true}`; neither id means all repos. The Ask page calls it with `force: false` when it opens. |
| `GET /drafts?project_id=…` or `?label=…` | history for a scope |
| `POST /drafts` | `{kind, label, project_id?}`: start or resume, returns the draft with its messages |
| `GET /drafts/{id}` | the draft and its messages |
| `PATCH /drafts/{id}` | `{sections}` (autosave) or `{period_start, period_end}` (change range, which regenerates) |
| `POST /drafts/{id}/messages` | `{content}`: runs one chat turn, returns the new assistant message and the updated draft |
| `POST /drafts/{id}/retry` | re-runs the turn for the last user message that has no reply (after a `502`) |
| `GET /drafts/{id}/discord` | `{text, over_limit}` |
| `POST /drafts/{id}/save` · `DELETE /drafts/{id}` | save; discard (in-progress only) |
| `GET /items?project_id=…` or `?label=…` | the open-items panel: open todos and blockers, plus the 5 most recent notes |
| `POST /notes` | `{text, label, project_id?}`: "Save answer as note" (recorded as an `ask_chat` batch) |
| `POST /batches/{id}/undo` | `{force?}`; returns `409` with conflicts when needed |
| `POST /ask` | `{messages}` → `{answer, terms, citations, batch_id?}` |
| `GET /settings` · `PUT /settings` | `{github_username, my_emails}` |
| `GET /settings/emails` | detected emails with counts and candidate reasons |

## 6. Error handling

**General rule:** a failure in one part (one repo, one AI call, one tool call) is reported where it happened, and everything else keeps working.

### OpenAI (`llm`)
| Situation | Behavior |
|---|---|
| `OPENAI_API_KEY` or `OPENAI_MODEL` missing | The app still starts. `/health` reports `api_key_loaded: false`, AI endpoints return `503 {"error": "ai_disabled"}`, and the UI shows the banner. |
| Rate limit, 5xx error or timeout | The SDK retries (`max_retries = 2`, 60-second timeout). After that, `llm` raises `LLMUnavailable`. Routes turn it into `502` and the UI shows **Retry** on the message. The user's chat message is already saved, so Retry (`POST /drafts/{id}/retry`) re-runs the turn without saving it again. |
| Auth error (bad key) | `502` with "OpenAI rejected the API key", plus a toast pointing to `.env`. No retry. |
| Malformed structured output | One retry with the validation error included. After that, `502`. |
| Failure in the middle of an agent turn | Writes that already happened stay and stay recorded in the batch. The assistant message is saved as "Stopped after an error · N changes applied", with Undo. |
| 10-round limit reached | Same as above, but worded "Stopped after 10 steps". |
| Bad tool arguments, label-lock miss, invalid transition | Returned to the model as a tool error string. The turn continues. |

### Git (`git_reader`, `sync`)
| Situation | Behavior |
|---|---|
| `git` not found at startup | Logged. `/health` reports `git_available: false`. Sync and repo-add endpoints return `503` with a clear message. |
| Adding a path that doesn't exist or isn't a work tree | `422`, with the reason shown inline in Settings. |
| Adding a path that's already registered | `409` "already added to ‹project›". |
| Repo folder missing during sync | `last_fetch_error = "folder missing"`. The repo is skipped and an amber chip appears. |
| Fetch fails (offline, auth, timeout) | The short reason is stored and the repo is skipped. Local commits are still read. |
| `git log` output that won't parse | That commit is logged and skipped. The rest of the batch is stored. |

### Data (`store`)
- **Atomic writes.** Each tool write and its `batch_changes` row, an undo, a relabel and a project delete each run in one transaction.
- **Constraint violations become HTTP errors.** Uniqueness, CHECK constraints and partial indexes are mapped to `409` or `422` with readable messages. A raw SQLite error is never passed to the client.
- **Migrations** run at startup inside a transaction. If one fails, the app refuses to start and logs the error, which is better than running on a half-migrated database.

### Drafts
- **Discord over 2,000 characters** after the one shorten retry: `over_limit: true`, with the red counter.
- **Saving an empty section** is allowed. On save, an empty section renders as "None."
- **Racing a second in-progress draft** for the same scope and kind: the partial unique index rejects it, and `POST /drafts` returns the existing draft instead.

### Frontend
- TanStack Query errors render inline in the component that owns the data, with a Retry button.
- Mutations that fail show a toast with the server's message.
- The Undo `409` opens the conflict dialog (§4.5) instead of a toast.

### Security
- Uvicorn binds to `127.0.0.1` only.
- CORS is disabled because the app is served from the same origin. The dev proxy makes development same-origin as well.
- The API key is read only by `config` and `llm`, and never appears in a response or a log line.
- `.env` and `*.db*` are gitignored. A `.env.example` with placeholder values is committed.

## 7. Testing

Implementation is test-first (red → green → refactor). **The whole suite runs offline.**

### Backend (pytest)
| Area | How it's tested |
|---|---|
| `git_reader` | Real temporary repos built with `git init`, with commits made under different author names and emails (via `GIT_AUTHOR_*` env vars), across several branches, including a merge commit (which must be excluded) and file changes. Fetch is tested against a local bare repo standing in for `origin`, plus a nonexistent remote to exercise the failure path. |
| `store` | Temporary SQLite files with migrations applied. Covers: CHECK constraints and transitions; FTS triggers (insert, update, delete, then search finds or no longer finds the row); the porter stemming match; join-time filtering by `my_emails`; the in-progress uniqueness rule; range start from the last saved `period_end`; relabel cascading to items; project deletion keeping items. |
| `sync` | Throttle (no fetch within 15 minutes unless forced); incremental reads with overlap and no duplicates; a missing folder; the lock (two concurrent calls fetch once). |
| `agent` | Driven by `FakeLLM` scripts: the label lock (another label's id is "not found"); project name resolution and the unknown-name error; invalid transitions; one batch per turn, created lazily; the 10-round stop; a mid-turn error keeping earlier writes. |
| Undo | Reverts newest-first; conflict detection → `409`; `force`; "already gone"; double undo rejected. |
| `drafts` | v1 includes every open item; the nudge round when `update_draft` is skipped; manual edits clear the Discord cache; the shorten retry and `over_limit`; save renders `record_text`; discard keeps item changes; previous-workday fallback (Monday → Friday). |
| `search` | Keyword extraction, then the OR query and top-15 ranking; the stop-word fallback on zero hits or a failed call; citation numbering; other authors' commits excluded. |
| Routes | FastAPI `TestClient` with `FakeLLM` injected through dependency overrides: status codes from §6, `ai_disabled`, the `409` paths. |

**Shared fixtures:**
- `tmp_db`
- `make_repo(commits=[...])`
- `fake_llm(script)`
- a frozen clock (`freezegun`), so date-range tests don't depend on the real day

**`FakeLLM`** is given an ordered list of responses (a text reply, tool calls, or a structured object) and records every input it receives, so tests can check what was sent, for example "every open item was in the prompt."

**Real API:** `scripts/smoke_openai.py` runs one draft and one Ask turn against the real API. It's opt-in and never part of `pytest`.

### Frontend
- **Vitest + React Testing Library** cover:
  - `DraftCard`: switching tabs, editing triggers autosave, the counter turns red over 2,000
  - `ChangeChips`/`UndoButton`: undo, the struck-through state, the conflict dialog on `409`
  - `SourceChips`: expand and collapse
  - the Settings email checklist: the "new" chip, and Save sends the checked list
- **API mocking:** `fetch` is mocked at the `api.ts` boundary.
- **`tsc --noEmit`** runs as part of the test command.
- No browser end-to-end tests in v1.

## 8. Configuration and repo layout

**`.env`** (gitignored; `.env.example` is committed):
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=<model name>
WEEKFEED_DB_PATH=./weekfeed.db      # optional
WEEKFEED_PORT=8765                  # optional
```

**Layout:**
```
WeekFeed/
  backend/
    src/weekfeed/   config, git_reader, store/, sync, llm, agent, drafts, search, api/
    tests/
    pyproject.toml
  frontend/         Vite + React + TS app (see §5.6)
  scripts/          smoke_openai.py
  docs/superpowers/ specs/, plans/
  .env.example  .gitignore  CLAUDE.md  README.md
```

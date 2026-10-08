# WeekFeed

A local, single-user web app (macOS, GitHub user `kdb82`) that:
- drafts standups and weekly updates from git commits and notes
- keeps a personal knowledge base you can chat with
- manages todos and blockers through an agent

It only drafts text. The user copies the text and posts it themselves.

**Status: v1 implemented.** The spec at `docs/superpowers/specs/2026-10-07-weekfeed-design.md` is the source of truth; read it before changing behaviour, and update it when a change alters the design.

## Commands

- Backend (from `backend/`): `uv run pytest` · `uv run weekfeed` (serves API + built frontend on 127.0.0.1:8765)
- Frontend (from `frontend/`): `npm test` (tsc + Vitest) · `npm run dev` (proxies `/api` to :8765) · `npm run build`

## Domain language

- **Label:** `work` | `school` | `personal`. Every project has exactly one.
- **Project:** a named group of local git repos (registered by folder path). Its repos and items inherit its label.
- **Scope:** what a draft or agent run covers. Either one project or a whole label.
- **Item:** `note` | `todo` | `blocker`.
  - Every item has a label and an optional project. An item tied to a project always carries that project's label.
  - Todos close as `done`. Blockers close as `resolved`.
- **My commits:** commits whose author email is in `settings.my_emails`. The list is auto-detected and confirmed by the user. Commits from all authors are stored, and filtering happens at query time.
- **Draft:** a standup or weekly update.
  - Status is `in_progress` or `saved`.
  - Each draft has a record version and a Discord version.
  - Its chat lives in `draft_messages`.
- **Batch:** all the item changes one agent message made. A batch is undone as a unit.
- **Sync:** `git fetch`, at most once every 15 minutes per repo, then reading new commits into SQLite.

## Stack

- **Backend:** Python + FastAPI, SQLite with FTS5 keyword search, and the OpenAI Responses API with tool calling.
- **Frontend:** Vite + React + TypeScript, React Router, TanStack Query, CSS modules.
- **Layout:** `backend/src/weekfeed/` (src layout, tests in `backend/tests/`), `frontend/src/`.
- **Running it:**
  - Daily use: FastAPI serves the built frontend and the API on one localhost URL.
  - Development: Vite proxies `/api` to FastAPI.

## Module boundaries

Git, database and OpenAI code each live in exactly one module, so any one of them can be swapped by editing a single module.

- `git_reader`: the only code that runs git (`log --all`, `fetch`).
- `store`: the only code that touches SQLite.
- `llm`: the only code that talks to OpenAI.
- `sync`: hands commits from `git_reader` to `store`.
- `agent`, `drafts`, `search`: orchestrate the modules above.
- Routes are thin glue. Logic lives in the modules.

## Invariants (enforced in code, never left to prompts)

**Agent**
- **Label lock:** agent tools only read and change items inside the run's scope label.
- Tool errors go back to the model as tool results.
- At most 10 rounds per message.

**Batches and undo**
- Each item change is written in the same transaction as its `batch_changes` row.
- Undo reverses a batch newest-first.
- If any of the batch's items were updated after the batch ran, Undo lists them and asks for confirmation first.

**Drafts**
- A draft's date range starts at the last *saved* draft of the same kind and scope. If there's none, it falls back to the previous workday for a standup, or 7 days for a weekly update.
- On every turn, the agent gets the current open items and includes each of them in Today/Next and Blockers.
- The Discord version uses bold headers and bullets, and stays under 2,000 characters.

**Git**
- `git fetch` runs with a 10-second timeout and `GIT_TERMINAL_PROMPT=0`.
- A failed fetch is recorded in `repos.last_fetch_error` and that repo is skipped.

**Security**
- The server binds to `127.0.0.1`.
- `OPENAI_API_KEY` and `OPENAI_MODEL` live in a gitignored `.env`. The key stays server-side.
- The SQLite file is gitignored.

## Testing

Work test-first. The suite runs fully offline:
- **LLM:** wherever `llm` is needed, use `FakeLLM`, which plays back scripted replies including tool calls. Real-API checks live in an opt-in smoke script.
- **git_reader:** tests use real temporary repos, plus a local bare repo standing in for the GitHub remote.
- **store:** tests use temporary SQLite files.
- **Frontend:** Vitest + React Testing Library on key components, plus `tsc`.

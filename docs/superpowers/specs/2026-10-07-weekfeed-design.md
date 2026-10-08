# WeekFeed design spec

- **Date:** 2026-10-07
- **Status:** draft, being written section by section
- **UI mockup:** https://claude.ai/artifact/3ydPGE9szXdq96Aay1mRwK

## 1. Overview

### Purpose
WeekFeed is a local web app for one person, Kaden (GitHub `kdb82`), running on their Mac. It turns the work they already record (git commits, quick notes, todos and blockers) into three things:

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

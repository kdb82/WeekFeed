# WeekFeed

A local-first web app that turns your git commits and quick notes into standups, weekly updates, and a searchable personal knowledge base, with an AI agent that manages your todos and blockers (and can undo anything it does).

## Status

**Design phase. No application code yet.** The design spec is being written section by section, and implementation starts once the spec and its implementation plan are approved. Follow along in [`docs/superpowers/specs/2026-10-07-weekfeed-design.md`](docs/superpowers/specs/2026-10-07-weekfeed-design.md).

## What it does

1. **Drafts standups and weekly updates.** Standups are Yesterday / Today / Blockers; weekly updates are Done / Next / Blockers. A draft covers one project or a whole label (work, school, personal) and spans everything since the last saved draft for that scope. Each draft has a full "record" version and a Discord-ready version (bold headers and bullets, under 2,000 characters). WeekFeed only drafts: you copy the text and post it yourself.
2. **Answers questions from your own history.** Ask things like "how did I fix the auth bug?" and an agent answers from your notes and commits, citing the sources it used, and says so when it can't find an answer.
3. **Manages todos and blockers conversationally.** While drafting, you chat with the agent to revise the draft and to add or close todos, blockers, and notes. Every set of changes it makes has a one-click Undo.

## Planned UI

- **Projects board:** projects in columns by label, each card showing its repos, open todo and blocker counts, last standup, and sync status.
- **Project page:** standup history sidebar, the drafting chat, an open-items panel, and a Sync button.
- **Ask page:** chat over the knowledge base, with answers that cite source notes and commits.
- **Settings:** projects, repos (registered by local folder path), an auto-detected "my commit emails" checklist, and API key status.

## How it works

```
Browser (React SPA)
   |  JSON over HTTP, 127.0.0.1 only
   v
FastAPI routes (thin)
   |
   +-- drafts --+
   +-- agent  --+--> llm --> OpenAI Responses API
   +-- search --+
   +-- sync ----------> git_reader --> git (subprocess)
   |
   +-- all of the above --> store --> SQLite (WAL, FTS5)
```

Commits are read from local clones (no GitHub API), with a throttled `git fetch` at most once every 15 minutes per repo. All authors' commits are stored, and "my commits" are filtered at query time by a user-confirmed list of author emails.

## Tech stack

- **Backend:** Python, FastAPI, SQLite with FTS5, OpenAI Responses API with tool calling
- **Frontend:** Vite, React, TypeScript, React Router, TanStack Query, CSS modules
- **Testing:** pytest (backend), Vitest + React Testing Library + `tsc` (frontend)

In daily use, FastAPI serves the built frontend and the API from one localhost URL. In development, the Vite dev server proxies `/api` to FastAPI.

## Design highlights

- **Tool-calling agent with undoable batches.** One shared agent loop (at most 10 rounds per message) is reused by the drafting chat and the Ask chat, each with its own tool set. Every item change an agent message makes is written in the same transaction as a change-log row, so the whole batch can be undone as a unit, newest change first. If an item was edited after the batch ran, Undo lists it and asks before reverting.
- **Label-scoped data isolation, enforced in code.** Every project and item carries exactly one label. Agent tools can only read and change items inside the current run's label, so work, school, and personal content never mix in a draft. This is a code-level guarantee, not a prompt instruction.
- **Keyword retrieval with citations.** The AI first expands a question into search keywords, SQLite FTS5 ranks matches with BM25, and the top 15 go to the model, which answers with `[n]` citations back to specific notes and commits. Search sits behind a single function so embedding-based search can replace it later.
- **Clean module boundaries.** Git, SQLite, and OpenAI each live in exactly one module (`git_reader`, `store`, `llm`), so any of them can be swapped by editing one file. `sync`, `agent`, `drafts`, and `search` orchestrate those modules, and API routes are thin glue.
- **Fully offline, test-first suite.** The `llm` module sits behind a `Protocol`, so tests use a `FakeLLM` that plays back scripted replies, including tool calls. Git tests run against real temporary repos plus a local bare repo standing in for the remote, and storage tests use temporary SQLite files. Real-API checks live in a separate opt-in smoke script.

## Privacy and local-first

- Single user, single machine. No accounts and no network exposure: the server binds to `127.0.0.1`.
- WeekFeed never posts anything to Discord, GitHub, or anywhere else. It only drafts text.
- The OpenAI API key lives in a gitignored `.env` and stays server-side; the browser never sees it.
- The SQLite database is a local, gitignored file.
- Note: draft and search context (commits, notes, items) is sent to the OpenAI API to generate text. A per-project opt-out is on the roadmap.

## Getting started

Setup instructions will be added with the first implementation. Planned prerequisites:

- Python (backend)
- Node.js (frontend build)
- git, with local clones of the repos you want to track
- An OpenAI API key, stored in a gitignored `.env`

## Roadmap

- [ ] Design spec (in progress)
- [ ] Implementation plan
- [ ] Backend: store, git reader, sync, LLM client, agent, drafts, search, API
- [ ] Frontend: projects board, project/drafting page, Ask page, settings

Deferred ideas:

- A per-project switch to keep that project's data from being sent to the API
- Embedding-based (meaning-based) search alongside or in place of keyword search

## Design docs

- [WeekFeed design spec](docs/superpowers/specs/2026-10-07-weekfeed-design.md): the source of truth for scope, architecture, and invariants

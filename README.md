# Cortec

**Local-first memory server for developer workflows.**

Cortec runs as an MCP server inside your coding environment. It remembers your project decisions, bugs, fixes, and session context — and retrieves exactly the right memory when you need it. Everything stays on your machine.

---

## The Problem

Every developer hits the same wall: you finish a session, start a new one, and spend the first 20 minutes re-explaining what was already figured out. What database you chose and why. What that bug was and how you fixed it. What you decided not to do. That context doesn't live anywhere — it just disappears.

## What Cortec Does

Cortec stores that context as structured memories and retrieves them semantically when you need them. You ask it a question, it finds the right answer from your own history.

```
cortec remember "We use Chroma for vector storage — simpler local setup than Qdrant" \
  --type decision --project myapp

cortec recall "vector database choice"
```

```
╭── 6474b9db  score=0.94  confidence=0.7 ──────────────────────────╮
│ We use Chroma for vector storage — simpler local setup than Qdrant │
╰── source=session  project=myapp  2026-05-25 ─────────────────────╯
```

---

## Install

```bash
pip install cortec-mcp
```

```bash
cortec init
cortec doctor
```

---

## Core Features

**Secret scanning** — before anything is stored, Cortec scans for API keys, tokens, passwords, and private keys. If it finds one, storage is blocked.

**Approval mode** — nothing is stored silently. By default, every memory goes through an approval step before it's indexed.

**Conflict detection** — if a new memory contradicts an existing one (Flask vs Django, Chroma vs Qdrant), Cortec flags it and asks you to resolve it before storing.

**Source citations** — every recalled memory tells you where it came from, when it was saved, and how confident the match is.

**Project isolation** — each project has its own memory space. A recall in one project never pulls from another.

**Memory types** — memories are categorized so you can filter by what you need:

| Type | What it stores |
|---|---|
| `decision` | A choice made about tech, design, or approach |
| `bug` | A bug or error encountered |
| `fix` | The solution that worked |
| `architecture` | A structural or design pattern decision |
| `preference` | A personal or team preference |
| `command` | A useful CLI command worth remembering |
| `dependency` | A library or package decision |
| `portfolio` | Something worth showcasing |
| `resume` | An achievement or skill |
| `general` | Anything else |

---

## MCP Tools

Cortec exposes these tools to your coding environment:

| Tool | Description |
|---|---|
| `remember` | Store a memory — scans secrets, checks conflicts, gates approval |
| `recall` | Semantic search across your memory — filter by project and type |
| `summarize_session` | Summarize and archive a session automatically |
| `list_memories` | Browse stored memories with citations |
| `project_context` | Load full project memory grouped by type at session start |
| `forget` | Permanently delete a memory |

---

## CLI

```bash
cortec remember "text" --type decision --project myapp
cortec recall "query" --type bug
cortec approve <id>
cortec conflicts
cortec resolve <id>
cortec status
cortec export
cortec doctor
cortec audit
```

---

## Confidence Scale

Every memory has a confidence score based on its source:

| Score | Source |
|---|---|
| 0.9 | User confirmed |
| 0.8 | GitHub commit or PR |
| 0.7 | Session summary |
| 0.6 | Stack Overflow pattern |
| 0.5 | Inferred |

---

## Current Status

**Phase 1 and Phase 2 are complete.**

- MCP server running with 6 tools
- SQLite metadata store + Chroma vector search
- Secret scanning (15 patterns), approval mode, conflict detection
- Full CLI with 11 commands
- 22 tests passing
- Local-first — no cloud, no telemetry, no external services

---

## Roadmap

**Phase 3 — GitHub integration**
Index your commits, PRs, and issues. Link memories to the code that caused or fixed them.

**Phase 4 — Stack Overflow pattern store**
When a Stack Overflow answer helps you fix something, store the pattern locally so you never have to search for it again.

**Phase 5 — Knowledge graph**
Connect memories across projects — bugs, fixes, files, decisions — into a navigable graph. Ask "what else is related to this?" and get real answers.

**Phase 6 — Agent workflows**
PR assistant, debugging assistant, and portfolio builder — all powered by your own memory.

---

## Privacy

- All data stays local — no cloud upload, ever
- Full export and delete support
- Per-project memory isolation
- `.cortec/` folders excluded from git by default

---

## License

MIT — Raj Kumar Satya

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
| `pattern` | A reusable solution pattern, often from Stack Overflow |
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
| `index_github_repo` | Index a repo's commits, PRs, and issues as memories |
| `link_memory_to_commit` | Link a memory to a specific commit SHA |
| `commits_for_memory` | Find all memories linked to the same commit |
| `store_so_pattern` | Fetch a Stack Overflow answer and store it as a pattern |
| `recall_patterns` | Semantic search over stored Stack Overflow patterns |
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
cortec github-index owner/repo --project myapp
cortec github-link <memory_id> <commit_sha>
cortec so-store https://stackoverflow.com/a/11227902
cortec so-search "async generator pattern"
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

**Phases 1, 2, 3, and 4 are complete.**

- MCP server with 11 tools
- SQLite metadata store + Chroma vector search
- Secret scanning (15 patterns), approval mode, conflict detection
- GitHub integration — index commits, PRs, and issues; link memories to commit SHAs
- Stack Overflow pattern store — fetch answers by URL, store and search locally
- Full CLI with 15 commands
- 53 tests passing
- Local-first — no cloud, no telemetry, no external services

---

## Roadmap

**Phase 4 — Stack Overflow pattern store**
When a Stack Overflow answer helps you fix something, store the pattern locally so you never have to search for it again.

**Phase 5 — Knowledge graph**
Connect memories across projects — bugs, fixes, files, decisions — into a navigable graph. Ask "what else is related to this?" and get real answers.

**Phase 6 — Agent workflows**
PR assistant, debugging assistant, and portfolio builder — all powered by your own memory.

---

## GitHub Integration

Index any GitHub repo directly into your memory store:

```bash
cortec github-index rajkumar-prog/cortec-mcp --project cortec
```

This pulls recent commits, pull requests, and issues and stores them as searchable memories. Commits get `confidence=0.8` — same as a verified GitHub source.

Link a memory you already have to the commit that caused or fixed it:

```bash
cortec github-link a1b2c3d4 79ac0d5e
```

Or use the MCP tools directly from your coding environment — `index_github_repo`, `link_memory_to_commit`, `commits_for_memory`.

---

## Stack Overflow Pattern Store

When a Stack Overflow answer solves your problem, save it so you never search for it again:

```bash
cortec so-store https://stackoverflow.com/a/11227902
```

Cortec fetches the question and accepted answer, strips the HTML, and stores it as a `pattern` memory with `confidence=0.6`. Later, search it semantically:

```bash
cortec so-search "close file descriptor python"
```

Or use the MCP tools directly — `store_so_pattern` and `recall_patterns` — from inside your coding environment.

---

## Privacy

- All data stays local — no cloud upload, ever
- Full export and delete support
- Per-project memory isolation
- `.cortec/` folders excluded from git by default

---

## License

MIT — Raj Kumar Satya

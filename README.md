# Cortec

**Local-first memory server for developer workflows.**

Cortec runs as an MCP server inside your coding environment. It remembers your project decisions, bugs, fixes, and session context and retrieves exactly the right memory when you need it. Everything stays on your machine.

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
| `build_graph` | Build a knowledge graph for a project and return its summary |
| `graph_neighbors` | Return memories connected to a given memory within N hops |
| `link_memories` | Explicitly link two memories in the knowledge graph |
| `draft_pr_summary` | Draft a PR description from project decisions, fixes, and bugs |
| `debug_suggest` | Find related bugs, fixes, and patterns for an error message |
| `build_portfolio` | Aggregate portfolio and resume memories into a Markdown export |
| `stale_memories` | List memories whose confidence has decayed below a threshold |
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
cortec graph-summary --project myapp
cortec graph-neighbors <memory_id> --depth 2
cortec graph-link <memory_id_a> <memory_id_b>
cortec pr-draft --project myapp --context "refactor auth layer"
cortec debug "TypeError: cannot unpack non-sequence NoneType"
cortec portfolio --project myapp
cortec portfolio --markdown
cortec stale --project myapp --threshold 0.4
```

---

## Confidence Scale

Every memory starts with a confidence score based on its source:

| Score | Source |
|---|---|
| 0.9 | User confirmed |
| 0.8 | GitHub commit or PR |
| 0.7 | Session summary |
| 0.6 | Stack Overflow pattern |
| 0.5 | Inferred |

That starting score then [decays with age](#memory-decay) — `recall` reports the effective confidence after decay, not just the original.

---

## Current Status

**Phases 1–7 are complete.**

- MCP server with 18 tools
- SQLite metadata store + Chroma vector search
- Secret scanning (15 patterns), approval mode, conflict detection
- GitHub integration — index commits, PRs, and issues; link memories to commit SHAs
- Stack Overflow pattern store — fetch answers by URL, store and search locally
- Knowledge graph — connect memories by explicit links, shared tags, and type; traverse with BFS
- Agent workflows — PR draft, debug assist, and portfolio builder from memory
- Memory decay — confidence ages toward a floor with per-type half-lives; stale memories surface in recall
- Full CLI with 22 commands
- 127 tests passing
- Local-first — no cloud, no telemetry, no external services

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

Cortec fetches content from the Stack Overflow URL (answer or question, using the best available answer), strips the HTML, and stores it as a `pattern` memory with `confidence=0.6`. Later, search it semantically:

```bash
cortec so-search "close file descriptor python"
```

Or use the MCP tools directly — `store_so_pattern` and `recall_patterns` — from inside your coding environment.

---

## Knowledge Graph

Memories are connected automatically based on shared tags, memory type, and explicit links. Traverse that graph to discover what else is related to any memory.

```bash
# See the shape of a project's memory graph
cortec graph-summary --project myapp

# Find what's connected to a specific memory (up to 2 hops away)
cortec graph-neighbors a1b2c3d4 --depth 2

# Manually link two memories you know are related
cortec graph-link a1b2c3d4 e5f6g7h8
```

Edges are weighted by connection strength:

| Weight | Reason |
|---|---|
| 1.0 | Explicit link (`graph-link` or `link_memories`) |
| 0.7 | Shared tag |
| 0.4 | Same memory type within the same project |

The `build_graph`, `graph_neighbors`, and `link_memories` MCP tools expose the same capability from inside your coding environment.

---

## Agent Workflows

Three memory-powered assistants that synthesize stored knowledge into actionable output — no LLM calls, everything runs locally.

### PR Draft

Pull the latest decisions, fixes, and bugs from memory and get a ready-to-paste PR description:

```bash
cortec pr-draft --project myapp
cortec pr-draft --project myapp --context "refactor auth middleware"
```

Or call `draft_pr_summary(project, context)` from your MCP environment.

### Debug Assist

Give Cortec an error message and it searches your stored bugs, fixes, and Stack Overflow patterns for relevant suggestions:

```bash
cortec debug "TypeError: 'NoneType' object is not subscriptable"
cortec debug "connection refused 5432" --project myapp
```

Results are ranked by semantic score and grouped by type (bug, fix, pattern). Call `debug_suggest(error, project)` from MCP.

### Portfolio Builder

Aggregate everything worth showcasing into a structured summary or Markdown export:

```bash
cortec portfolio --project myapp
cortec portfolio --markdown > portfolio.md
```

Store portfolio items as you work:

```bash
cortec remember "Built semantic search over 10M tokens in < 200ms" --type portfolio
cortec remember "Led migration from Django to FastAPI, 3x throughput gain" --type resume
```

Call `build_portfolio(project)` from MCP to get the same output programmatically.

---

## Memory Decay

Old context shouldn't be trusted as much as fresh context. Cortec ages each memory's confidence toward a floor over time, so a decision you made 18 months ago no longer outranks one from last week.

Decay is computed at read time — the stored confidence is never overwritten. It's treated as immutable provenance, and decay is a lens applied on top:

```
effective = floor + (base − floor) × 0.5 ^ (age_days / half_life)
```

Each memory type has its own half-life, so timeless context decays slowly and volatile context decays fast:

| Half-life | Types |
|---|---|
| 365 days | `architecture`, `resume`, `portfolio` |
| 270 days | `decision`, `preference` |
| 120 days | `dependency`, `command`, `general` |
| 90 days | `pattern`, `fix` |
| 60 days | `bug` |

`recall` reports the decayed value (`confidence=0.8→0.52`) and flags anything below the stale threshold. To review what's gone stale and prune it:

```bash
cortec stale --project myapp
cortec stale --threshold 0.5
```

Or call `stale_memories(project, threshold)` from MCP.

---

## Privacy

- All data stays local — no cloud upload, ever
- Full export and delete support
- Per-project memory isolation
- `.cortec/` folders excluded from git by default

---

## License

MIT — Raj Kumar Satya

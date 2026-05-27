# Cortec

Local-first memory server for developer workflows.

Cortec captures your project decisions, bugs, fixes, and session context — then retrieves exactly the right memory when you need it, without ever leaving your machine.

## Install

```bash
pip install cortec-mcp
```

## Quick Start

```bash
cortec init
cortec remember "We use Chroma for vector storage" --type decision --project myapp
cortec recall "vector database decision" --project myapp
cortec status
cortec doctor
```

## MCP Tools

| Tool | Description |
|---|---|
| `remember` | Store a memory with secret scanning and approval gate |
| `recall` | Semantic search — filter by project and type |
| `summarize_session` | Summarize and archive a session |
| `list_memories` | List memories with source citations |
| `forget` | Permanently delete a memory |
| `project_context` | Full project memory grouped by type |

## CLI Commands

| Command | Description |
|---|---|
| `cortec init` | Initialize for a project |
| `cortec remember` | Store a memory |
| `cortec recall` | Search memories |
| `cortec approve` | Approve a pending memory |
| `cortec forget` | Delete a memory |
| `cortec conflicts` | View unresolved conflicts |
| `cortec resolve` | Resolve a conflict |
| `cortec status` | Memory counts + type breakdown |
| `cortec export` | Export all memories to JSON |
| `cortec doctor` | Health check |
| `cortec audit` | Full audit report |

## Memory Types

| Type | Description |
|---|---|
| `decision` | Tech or design choice made |
| `bug` | Bug or error encountered |
| `fix` | Solution applied to a bug |
| `architecture` | Structural or pattern decision |
| `preference` | Team or personal preference |
| `command` | Useful CLI command to remember |
| `dependency` | Package or library decision |
| `portfolio` | Worth showcasing |
| `resume` | Achievement or skill |
| `general` | Anything else |

## Confidence Scale

| Score | Source |
|---|---|
| 0.9 | User confirmed |
| 0.8 | GitHub commit or PR |
| 0.7 | Session summary |
| 0.6 | Stack Overflow pattern |
| 0.5 | Inferred |

## Privacy

- All data stays local — no cloud upload, ever
- Secret scanning (14 patterns) before every store
- Full export and delete support
- Approval mode by default — nothing stored silently
- Per-project isolation via `.cortec/` folder

## License

MIT — Raj Kumar Satya

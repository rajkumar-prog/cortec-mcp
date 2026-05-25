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
cortec remember "We use Chroma for vector storage in the MVP"
cortec recall "vector database decision"
cortec status
cortec doctor
```

## MCP Tools

| Tool | Description |
|---|---|
| `remember` | Store a memory with secret scanning and approval gate |
| `recall` | Semantic search over stored memories |
| `summarize_session` | Summarize and archive a session |
| `list_memories` | List memories with citations |
| `forget` | Permanently delete a memory |

## Privacy

- All data stays local — no cloud upload, ever
- Secret scanning before every store
- Full export and delete support
- Approval mode by default (nothing stored silently)

## License

MIT — Raj Kumar Satya

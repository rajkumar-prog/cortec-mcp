# CORTEC.md

project: cortec-mcp
author: Raj Kumar Satya
version: 0.1.0
phase: 1

## Stack
- MCP server: FastMCP
- Vector DB: Chroma
- Metadata: SQLite
- Archive: JSONL
- Secret scan: detect-secrets

## Key Decisions
- Use Chroma over Qdrant for MVP (simpler local setup)
- Approval mode default: approval_required (never store silently)
- Confidence scoring: source-based (0.5 to 0.9)
- summarize_session: extractive MVP, LLM endpoint optional
- Secret scan runs before every store — no exceptions
- No external cloud services by default

## Confidence Scale
- 0.9: user confirmed
- 0.8: GitHub commit or PR
- 0.7: session summary
- 0.6: Stack Overflow pattern
- 0.5: inferred

## Privacy Rules
- All data stays local
- User can delete any memory
- User can export all memories
- Secrets are redacted before storing
- No telemetry, no analytics, no cloud sync

## Phase Roadmap
- Phase 1: MCP server + RAG + CLI
- Phase 2: Project memory types + conflict detection
- Phase 3: GitHub integration
- Phase 4: Stack Overflow pattern store
- Phase 5: Knowledge graph
- Phase 6: Agent workflows (current)

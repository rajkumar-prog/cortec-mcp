# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-07

### Added
- **`cortec browse`** — an interactive terminal browser for the memory store.
  Page through memories and filter by project or type, full-text search summaries,
  open a memory for full detail, and forget one in place. Stale memories are
  highlighted with their effective confidence and age. Filter, paginate, and
  command-parsing logic live in `cortec/browse.py` and are fully unit-tested.

## [0.2.1] - 2026-10-07

### Changed
- Corrected the package author email in project metadata.
- Added PyPI, CI, Python-version, and license badges to the README.
- Added this changelog and GitHub repository topics.

## [0.2.0] - 2026-10-07

### Added
- **Memory decay** — a memory's confidence now ages toward a floor over time with
  per-type half-lives (timeless decisions decay slowly, volatile bugs fast).
  `recall` reports the effective, decayed confidence and flags stale memories.
  New `stale_memories` MCP tool and `cortec stale` CLI command.
- **`cortec serve`** — launches the stdio MCP server; README documents registering
  it with any MCP-compatible client via an `mcpServers` config block.
- **Local-LLM session summarization** — `summarize_session` can use a local
  OpenAI-compatible LLM (e.g. Ollama) with graceful fallback to extractive.
- **Continuous integration** — test suite runs on every push and PR across
  Python 3.10, 3.11, and 3.12.
- **MIT LICENSE** file.

### Changed
- `cortec.__version__` is now derived from installed package metadata instead of a
  hardcoded constant, so it can never drift from the release version.

## [0.1.0] - 2026-06-30

### Added
- Core memory server (FastMCP + Chroma + SQLite + JSONL archive).
- Secret scanning, approval mode, and conflict detection.
- GitHub integration — index commits, PRs, and issues; link memories to commits.
- Stack Overflow pattern store — fetch answers by URL, store and search locally.
- Knowledge graph — connect memories by explicit links, shared tags, and type,
  with BFS traversal.
- Agent workflows — PR draft, debug assist, and portfolio builder from memory.
- Full CLI and 17 MCP tools.

[0.3.0]: https://github.com/rajkumar-prog/cortec-mcp/releases/tag/v0.3.0
[0.2.1]: https://github.com/rajkumar-prog/cortec-mcp/releases/tag/v0.2.1
[0.2.0]: https://github.com/rajkumar-prog/cortec-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/rajkumar-prog/cortec-mcp/releases/tag/v0.1.0

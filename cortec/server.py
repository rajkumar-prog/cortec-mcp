"""
Cortec MCP server — exposes memory tools to developer workflows.
"""

import json

import httpx
from fastmcp import FastMCP

from .config import (
    ApprovalMode,
    Confidence,
    CortecPaths,
    DEFAULT_APPROVAL_MODE,
    DEFAULT_PROJECT,
    RECALL_TOP_K,
    validate_type,
)
from .agents import pr_assistant, debug_assistant, portfolio as portfolio_agent
from .conflicts import detect as detect_conflict
from . import graph as graph_module
from .github import fetch_commits, fetch_prs, fetch_issues
from .ingest import archive_session, summarize
from .stackoverflow import fetch_from_url, build_pattern_summary, canonical_url
from .security.scanner import scan
from .security.redactor import redact
from .storage.db import MetadataStore
from .storage.vector import VectorStore


paths = CortecPaths()
paths.init()

db = MetadataStore(paths.db)
vector = VectorStore(paths.chroma)

mcp = FastMCP(
    name="cortec",
    instructions=(
        "Cortec is a local-first memory server for developer workflows. "
        "Use it to store and retrieve decisions, bugs, fixes, and project context. "
        "Always call recall before suggesting changes to an existing project."
    ),
)


@mcp.tool()
def remember(
    text: str,
    project: str = DEFAULT_PROJECT,
    tags: list[str] | None = None,
    type: str = "general",
    source: str = "session",
    related_files: list[str] | None = None,
    mode: str = DEFAULT_APPROVAL_MODE,
) -> dict:
    """Store a memory. Scans for secrets, checks for conflicts, then stores."""
    try:
        type = validate_type(type)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}

    clean_text = redact(text)

    result = scan(clean_text)
    if not result.clean:
        return {
            "status": "blocked",
            "reason": f"Secret scan failed: {', '.join(result.findings)}. Redact before storing.",
        }

    confidence = Confidence.from_source(source)

    existing = db.list_all(project=project, approved_only=True)
    conflict = detect_conflict(
        new_text=clean_text,
        existing_memories=existing,
        project=project,
        type_=type,
    )
    if conflict.found:
        conflict_id = db.flag_conflict(
            memory_id_a=conflict.existing_id,
            description=conflict.description,
        )
        return {
            "status": "conflict_detected",
            "conflict_id": conflict_id,
            "description": conflict.description,
            "action": "Resolve the conflict first, then store the memory.",
        }

    approved = mode == ApprovalMode.AUTO

    memory_id = db.insert(
        summary=clean_text,
        project=project,
        type_=type,
        source=source,
        confidence=confidence,
        tags=tags or [],
        related_files=related_files or [],
        approved=approved,
        raw_text=clean_text,
    )

    if approved:
        vector.add(
            memory_id=memory_id,
            text=clean_text,
            metadata={"project": project, "type": type, "source": source},
        )
        return {
            "id": memory_id,
            "status": "stored",
            "confidence": confidence,
            "project": project,
            "message": f"Memory {memory_id} stored and indexed.",
        }

    return {
        "id": memory_id,
        "status": "pending",
        "confidence": confidence,
        "project": project,
        "message": f"Memory {memory_id} queued for approval. Run: cortec approve {memory_id}",
    }


@mcp.tool()
def recall(
    query: str,
    project: str | None = None,
    type: str | None = None,
    top_k: int = RECALL_TOP_K,
) -> dict:
    """Search memories semantically. Filter by project and/or type."""
    if vector.count() == 0:
        return {"results": [], "message": "No memories stored yet. Use remember() first."}

    if type:
        try:
            type = validate_type(type)
        except ValueError as e:
            return {"status": "error", "reason": str(e)}

    hits = vector.search(query=query, top_k=top_k, project=project, type_=type)
    results = []
    for hit in hits:
        meta = db.get(hit["id"])
        if not meta:
            continue
        results.append({
            "id": hit["id"],
            "summary": hit["document"],
            "score": hit["score"],
            "citation": {
                "source": meta.get("source"),
                "project": meta.get("project"),
                "type": meta.get("type"),
                "created_at": meta.get("created_at"),
                "confidence": meta.get("confidence"),
                "related_files": json.loads(meta.get("related_files", "[]")),
                "tags": json.loads(meta.get("tags", "[]")),
            },
        })

    return {"query": query, "results": results, "count": len(results)}


@mcp.tool()
def summarize_session(
    text: str,
    project: str = DEFAULT_PROJECT,
    llm_endpoint: str | None = None,
    llm_model: str | None = None,
    auto_store: bool = False,
) -> dict:
    """Summarize a raw session and optionally store the result as a memory."""
    archive_path = archive_session(text, project, paths.archive)
    summary = summarize(text, llm_endpoint=llm_endpoint, llm_model=llm_model)

    result = {
        "summary": summary,
        "project": project,
        "archive_path": str(archive_path),
    }

    if auto_store:
        result["memory"] = remember(
            text=summary,
            project=project,
            type="general",
            source="session",
        )

    return result


@mcp.tool()
def list_memories(
    project: str | None = None,
    include_pending: bool = False,
) -> dict:
    """List stored memories with citations."""
    memories = db.list_all(project=project, approved_only=not include_pending)
    counts = db.count(project=project)

    formatted = []
    for m in memories:
        formatted.append({
            "id": m["id"],
            "summary": m["summary"][:120] + ("…" if len(m["summary"]) > 120 else ""),
            "type": m["type"],
            "project": m["project"],
            "confidence": m["confidence"],
            "approved": bool(m["approved"]),
            "created_at": m["created_at"],
            "source": m["source"],
            "tags": json.loads(m.get("tags", "[]")),
        })

    return {"memories": formatted, "counts": counts}


@mcp.tool()
def project_context(project: str) -> dict:
    """Return all memories for a project grouped by type. Use at session start."""
    memories = db.list_all(project=project, approved_only=True)

    if not memories:
        return {
            "project": project,
            "message": f"No memories found for project '{project}'.",
            "context": {},
            "total": 0,
        }

    grouped: dict[str, list] = {}
    for m in memories:
        t = m.get("type", "general")
        if t not in grouped:
            grouped[t] = []
        grouped[t].append({
            "id": m["id"],
            "summary": m["summary"],
            "confidence": m["confidence"],
            "source": m["source"],
            "created_at": m["created_at"][:10],
        })

    return {
        "project": project,
        "total": len(memories),
        "type_counts": {t: len(items) for t, items in grouped.items()},
        "context": grouped,
    }


@mcp.tool()
def index_github_repo(
    repo: str,
    project: str = DEFAULT_PROJECT,
    commits: int = 20,
    prs: int = 10,
    issues: int = 10,
) -> dict:
    """
    Index a GitHub repo's commits, PRs, and issues as memories.
    repo format: owner/repo (e.g. rajkumar-prog/cortec-mcp)
    """
    stored = []
    skipped = []

    def _store(summary: str, type_: str, source: str, sha: str | None = None) -> None:
        """Redact, scan, and store a single memory entry."""
        clean = redact(summary)
        if not scan(clean).clean:
            skipped.append(summary[:60])
            return
        mid = db.insert(
            summary=clean,
            project=project,
            type_=type_,
            source=source,
            confidence=0.8,
            approved=True,
            commit_sha=sha,
        )
        vector.add(mid, clean, {"project": project, "type": type_, "source": source})
        stored.append(mid)

    errors = []

    try:
        for c in fetch_commits(repo, limit=commits):
            if c.message.strip():
                _store(
                    f"[{c.sha}] {c.message} — by {c.author} on {c.date[:10]}",
                    type_="fix",
                    source="github_commit",
                    sha=c.sha,
                )
    except RuntimeError as e:
        errors.append(f"commits: {e}")

    try:
        for pr in fetch_prs(repo, limit=prs):
            text = f"PR #{pr.number}: {pr.title}"
            if pr.body:
                text += f"\n{pr.body}"
            _store(text, type_="fix", source="github_pr")
    except RuntimeError as e:
        errors.append(f"prs: {e}")

    try:
        for issue in fetch_issues(repo, limit=issues):
            text = f"Issue #{issue.number} ({issue.state}): {issue.title}"
            if issue.body:
                text += f"\n{issue.body}"
            _store(text, type_="bug", source="github_issue")
    except RuntimeError as e:
        errors.append(f"issues: {e}")

    return {
        "repo": repo,
        "project": project,
        "stored": len(stored),
        "skipped": len(skipped),
        "memory_ids": stored,
        "errors": errors,
    }


@mcp.tool()
def link_memory_to_commit(memory_id: str, commit_sha: str) -> dict:
    """Link an existing memory to a specific GitHub commit SHA."""
    meta = db.get(memory_id)
    if not meta:
        return {"status": "not_found", "memory_id": memory_id}
    updated = db.link_to_commit(memory_id, commit_sha)
    if updated:
        return {
            "status": "linked",
            "memory_id": memory_id,
            "commit_sha": commit_sha,
            "summary": meta["summary"][:100],
        }
    return {"status": "error", "message": "Failed to link memory to commit."}


@mcp.tool()
def commits_for_memory(memory_id: str) -> dict:
    """Return the commit SHA and any other memories linked to the same commit."""
    meta = db.get(memory_id)
    if not meta:
        return {"status": "not_found", "memory_id": memory_id}
    sha = meta.get("commit_sha")
    if not sha:
        return {"status": "no_commit", "memory_id": memory_id, "message": "No commit linked to this memory."}
    related = db.get_by_commit(sha)
    return {
        "memory_id": memory_id,
        "commit_sha": sha,
        "related_memories": [
            {"id": m["id"], "summary": m["summary"][:100]}
            for m in related if m["id"] != memory_id
        ],
    }


@mcp.tool()
def store_so_pattern(
    url: str,
    project: str = DEFAULT_PROJECT,
    tags: list[str] | None = None,
) -> dict:
    """
    Fetch a Stack Overflow answer or question and store it as a pattern memory.
    Provide the full Stack Overflow URL — answer or question link both work.
    """
    # Normalise to canonical form so /a/123 and /questions/456#123 are treated as the same
    url = canonical_url(url)

    # Check for duplicate
    existing = db.get_by_so_url(url)
    if existing:
        return {
            "status": "duplicate",
            "memory_id": existing["id"],
            "message": f"This URL is already stored as memory {existing['id']}.",
        }

    try:
        content = fetch_from_url(url)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    except httpx.RequestError as e:
        return {"status": "error", "reason": f"Network error fetching from Stack Overflow: {e}"}
    except RuntimeError as e:
        return {"status": "error", "reason": str(e)}

    summary = build_pattern_summary(content)
    clean = redact(summary)

    if not scan(clean).clean:
        return {"status": "blocked", "reason": "Secret scan failed on fetched content."}

    memory_id = db.insert(
        summary=clean,
        project=project,
        type_="pattern",
        source="stackoverflow",
        confidence=Confidence.STACKOVERFLOW,
        tags=tags or [],
        approved=True,
        so_url=url,
    )
    vector.add(memory_id, clean, {"project": project, "type": "pattern", "source": "stackoverflow"})

    return {
        "status": "stored",
        "memory_id": memory_id,
        "url": url,
        "summary": clean[:200],
        "confidence": Confidence.STACKOVERFLOW,
    }


@mcp.tool()
def recall_patterns(
    query: str,
    project: str | None = None,
    top_k: int = RECALL_TOP_K,
) -> dict:
    """Search stored Stack Overflow patterns semantically. Returns patterns with source URLs."""
    if vector.count() == 0:
        return {"results": [], "message": "No memories stored yet."}

    hits = vector.search(query=query, top_k=top_k, project=project, type_="pattern")
    results = []
    for hit in hits:
        meta = db.get(hit["id"])
        if not meta:
            continue
        results.append({
            "id": hit["id"],
            "summary": hit["document"],
            "score": hit["score"],
            "so_url": meta.get("so_url"),
            "confidence": meta.get("confidence"),
            "project": meta.get("project"),
            "created_at": meta.get("created_at", "")[:10],
        })

    return {"query": query, "results": results, "count": len(results)}


@mcp.tool()
def build_graph(project: str = DEFAULT_PROJECT) -> dict:
    """
    Build a knowledge graph of all memories in a project.

    Returns a summary of the graph structure — node count, edge count,
    connected components, and the most-connected memory.
    Edges are drawn from explicit links, shared tags, and shared type.
    """
    memories = db.list_all(project=project, approved_only=True)
    if not memories:
        return {
            "project": project,
            "nodes": 0,
            "edges": 0,
            "components": 0,
            "largest_component": 0,
            "most_connected": None,
            "edge_breakdown": {},
            "message": "No memories found.",
        }

    G = graph_module.build(memories)
    result = graph_module.summary(G)
    result["project"] = project
    return result


@mcp.tool()
def graph_neighbors(memory_id: str, depth: int = 1) -> dict:
    """
    Return memories connected to the given memory within `depth` hops.

    Builds the full graph for the memory's project, then traverses up to
    `depth` hops from the starting node. Each result includes the connection
    reason (explicit, shared_tag, same_type) and edge weight.
    """
    meta = db.get(memory_id)
    if not meta:
        return {"status": "not_found", "memory_id": memory_id}

    project = meta.get("project", DEFAULT_PROJECT)
    memories = db.list_all(project=project, approved_only=True)
    G = graph_module.build(memories)
    nbs = graph_module.neighbors(G, memory_id, depth=depth)

    return {
        "memory_id": memory_id,
        "summary": meta.get("summary", "")[:100],
        "depth": depth,
        "neighbors": nbs,
        "count": len(nbs),
    }


@mcp.tool()
def link_memories(memory_id_a: str, memory_id_b: str) -> dict:
    """Explicitly link two memories so they appear as related in the knowledge graph."""
    if not db.get(memory_id_a):
        return {"status": "not_found", "memory_id": memory_id_a}
    if not db.get(memory_id_b):
        return {"status": "not_found", "memory_id": memory_id_b}

    linked = db.link_memories(memory_id_a, memory_id_b)
    if linked:
        return {
            "status": "linked",
            "memory_id_a": memory_id_a,
            "memory_id_b": memory_id_b,
        }
    return {"status": "error", "message": "Failed to link memories."}


@mcp.tool()
def draft_pr_summary(
    project: str = DEFAULT_PROJECT,
    context: str = "",
    top_k: int = RECALL_TOP_K,
) -> dict:
    """
    Draft a PR summary for a project using its stored memories.

    Pulls recent decisions, fixes, bugs, and architecture memories, then
    optionally runs a semantic search against `context` to surface the most
    relevant entries. Returns a `template` field containing ready-to-paste
    GitHub PR markdown.
    """
    if top_k < 1:
        return {"status": "error", "reason": "top_k must be at least 1."}
    return pr_assistant.draft(db, vector, project=project, context=context, top_k=top_k)


@mcp.tool()
def debug_suggest(
    error: str,
    project: str | None = None,
    top_k: int = RECALL_TOP_K,
) -> dict:
    """
    Suggest fixes for an error or symptom from stored memory.

    Searches bug, fix, and Stack Overflow pattern memories semantically and
    returns ranked suggestions with source citations. Pass the raw error
    message or a short description of the symptom.
    """
    if top_k < 1:
        return {"status": "error", "reason": "top_k must be at least 1."}
    return debug_assistant.suggest(db, vector, error=error, project=project, top_k=top_k)


@mcp.tool()
def build_portfolio(project: str | None = None) -> dict:
    """
    Build a portfolio summary from portfolio and resume memories.

    Aggregates all portfolio, resume, decision, and architecture memories for
    a project (or all projects if project is None). Returns grouped lists and
    a `markdown` field with a ready-to-export portfolio document.
    """
    return portfolio_agent.build(db, project=project)


@mcp.tool()
def forget(memory_id: str) -> dict:
    """Permanently delete a memory from both the metadata store and vector index."""
    deleted = db.delete(memory_id)
    vector.delete(memory_id)

    if deleted:
        return {"status": "deleted", "id": memory_id}
    return {"status": "not_found", "id": memory_id}


def serve():
    """Start the Cortec MCP server."""
    mcp.run()


if __name__ == "__main__":
    serve()

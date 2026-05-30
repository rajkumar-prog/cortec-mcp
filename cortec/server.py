"""
Cortec MCP server — exposes memory tools to developer workflows.
"""

import json

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
from .conflicts import detect as detect_conflict
from .github import fetch_commits, fetch_prs, fetch_issues
from .ingest import archive_session, summarize
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
def forget(memory_id: str) -> dict:
    """Permanently delete a memory from both the metadata store and vector index."""
    deleted = db.delete(memory_id)
    vector.delete(memory_id)

    if deleted:
        return {"status": "deleted", "id": memory_id}
    return {"status": "not_found", "id": memory_id}


def serve():
    mcp.run()


if __name__ == "__main__":
    serve()

"""
Cortec MCP server — exposes memory tools to developer workflows.
"""

import json
from pathlib import Path

from fastmcp import FastMCP

from .config import (
    ApprovalMode,
    Confidence,
    CortecPaths,
    DEFAULT_APPROVAL_MODE,
    DEFAULT_PROJECT,
    MEMORY_TYPES,
    RECALL_TOP_K,
    validate_type,
)
from .ingest import archive_session, summarize
from .security.scanner import assert_clean, scan
from .security.redactor import redact
from .storage.db import MetadataStore
from .storage.vector import VectorStore


# ── Bootstrap ─────────────────────────────────────────────────────────────────

paths = CortecPaths()
paths.init()

db     = MetadataStore(paths.db)
vector = VectorStore(paths.chroma)

mcp = FastMCP(
    name="cortec",
    instructions=(
        "Cortec is a local-first memory server for developer workflows. "
        "Use it to store and retrieve decisions, bugs, fixes, and project context. "
        "Always call recall before suggesting changes to an existing project."
    ),
)


# ── Tool: remember ────────────────────────────────────────────────────────────

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
    """
    Store a memory. Runs secret scan before storing.
    In approval_required mode (default), memory is queued — not active until approved.

    Args:
        text:          The content to remember.
        project:       Project name for isolation (default: 'default').
        tags:          Optional tags for filtering.
        type:          Memory type: decision | bug | fix | architecture | preference | command | dependency | general.
        source:        Where this came from: session | github | stackoverflow | user.
        related_files: File paths this memory relates to.
        mode:          auto | manual | approval_required (default).

    Returns:
        id, status, confidence, message.
    """
    # 0. Validate memory type
    try:
        type = validate_type(type)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}

    # 1. Redact secrets first
    clean_text = redact(text)

    # 2. Scan — block if secrets still detected
    result = scan(clean_text)
    if not result.clean:
        return {
            "status": "blocked",
            "reason": f"Secret scan failed: {', '.join(result.findings)}. Redact before storing.",
        }

    # 3. Compute confidence from source
    confidence = Confidence.from_source(source)

    # 4. Determine approval state
    approved = mode == ApprovalMode.AUTO

    # 5. Store metadata
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

    # 6. If approved, index in vector store immediately
    if approved:
        vector.add(
            memory_id=memory_id,
            text=clean_text,
            metadata={"project": project, "type": type, "source": source},
        )
        status = "stored"
        message = f"Memory {memory_id} stored and indexed."
    else:
        status = "pending"
        message = (
            f"Memory {memory_id} queued for approval. "
            f"Run: cortec approve {memory_id}"
        )

    return {
        "id": memory_id,
        "status": status,
        "confidence": confidence,
        "project": project,
        "message": message,
    }


# ── Tool: recall ──────────────────────────────────────────────────────────────

@mcp.tool()
def recall(
    query: str,
    project: str | None = None,
    type: str | None = None,
    top_k: int = RECALL_TOP_K,
) -> dict:
    """
    Retrieve memories semantically matching the query.
    Returns results with source citations and confidence scores.

    Args:
        query:   What to search for.
        project: Limit search to a specific project (optional).
        type:    Filter by memory type: decision | bug | fix | architecture | preference | command | dependency | portfolio | resume | general.
        top_k:   Number of results to return (default: 5).

    Returns:
        List of matching memories with citations.
    """
    if vector.count() == 0:
        return {"results": [], "message": "No memories stored yet. Use remember() first."}

    # Validate type filter if provided
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
        results.append(
            {
                "id":           hit["id"],
                "summary":      hit["document"],
                "score":        hit["score"],
                "citation": {
                    "source":      meta.get("source"),
                    "project":     meta.get("project"),
                    "type":        meta.get("type"),
                    "created_at":  meta.get("created_at"),
                    "confidence":  meta.get("confidence"),
                    "related_files": json.loads(meta.get("related_files", "[]")),
                    "tags":        json.loads(meta.get("tags", "[]")),
                },
            }
        )
    return {
        "query":   query,
        "results": results,
        "count":   len(results),
    }


# ── Tool: summarize_session ───────────────────────────────────────────────────

@mcp.tool()
def summarize_session(
    text: str,
    project: str = DEFAULT_PROJECT,
    llm_endpoint: str | None = None,
    llm_model: str | None = None,
    auto_store: bool = False,
) -> dict:
    """
    Summarize a raw session and optionally store the summary as a memory.

    Args:
        text:         Raw session content to summarize.
        project:      Project this session belongs to.
        llm_endpoint: Optional local LLM endpoint (OpenAI-compatible, e.g. Ollama).
        llm_model:    Model name for the LLM endpoint.
        auto_store:   If True, immediately queue the summary as a memory.

    Returns:
        summary, archive_path, and optionally a memory_id if auto_store=True.
    """
    # Archive raw session first (always)
    archive_path = archive_session(text, project, paths.archive)

    # Summarize
    summary = summarize(text, llm_endpoint=llm_endpoint, llm_model=llm_model)

    result: dict = {
        "summary":      summary,
        "project":      project,
        "archive_path": str(archive_path),
    }

    if auto_store:
        store_result = remember(
            text=summary,
            project=project,
            type="general",
            source="session",
        )
        result["memory"] = store_result

    return result


# ── Tool: list_memories ───────────────────────────────────────────────────────

@mcp.tool()
def list_memories(
    project: str | None = None,
    include_pending: bool = False,
) -> dict:
    """
    List stored memories with source citations.

    Args:
        project:         Filter by project name (optional).
        include_pending: Include memories awaiting approval.

    Returns:
        List of memories and counts.
    """
    memories = db.list_all(project=project, approved_only=not include_pending)
    counts   = db.count(project=project)

    formatted = []
    for m in memories:
        formatted.append(
            {
                "id":         m["id"],
                "summary":    m["summary"][:120] + ("…" if len(m["summary"]) > 120 else ""),
                "type":       m["type"],
                "project":    m["project"],
                "confidence": m["confidence"],
                "approved":   bool(m["approved"]),
                "created_at": m["created_at"],
                "source":     m["source"],
                "tags":       json.loads(m.get("tags", "[]")),
            }
        )
    return {
        "memories": formatted,
        "counts":   counts,
    }


# ── Tool: forget ──────────────────────────────────────────────────────────────

@mcp.tool()
def forget(memory_id: str) -> dict:
    """
    Permanently delete a memory by ID.
    Removes from both metadata store and vector index.

    Args:
        memory_id: The ID of the memory to delete.

    Returns:
        Status of deletion.
    """
    meta_deleted   = db.delete(memory_id)
    vector.delete(memory_id)

    if meta_deleted:
        return {"status": "deleted", "id": memory_id}
    return {"status": "not_found", "id": memory_id}


# ── Entry point ───────────────────────────────────────────────────────────────

def serve():
    mcp.run()


if __name__ == "__main__":
    serve()

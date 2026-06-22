"""
Debug assistant — finds related bugs, fixes, and patterns from memory.

Given an error message or symptom, searches the memory store and returns
ranked suggestions grouped by type (bug, fix, pattern).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage.db import MetadataStore
    from ..storage.vector import VectorStore


def suggest(
    db: "MetadataStore",
    vector: "VectorStore",
    error: str,
    project: str | None = None,
    top_k: int = 5,
) -> dict:
    """
    Return ranked debug suggestions for a given error or symptom.

    Searches bugs, fixes, and Stack Overflow patterns separately so each
    category gets fair representation. Results are deduplicated by ID and
    sorted by semantic score descending.
    """
    if vector.count() == 0:
        return {
            "error": error,
            "project": project,
            "suggestions": [],
            "count": 0,
            "message": "No memories stored yet.",
        }

    raw: list[dict] = []

    for type_ in ("bug", "fix", "pattern"):
        hits = vector.search(error, top_k=top_k, project=project, type_=type_)
        for hit in hits:
            meta = db.get(hit["id"])
            if not meta:
                continue
            entry: dict = {
                "id": hit["id"],
                "type": type_,
                "summary": hit["document"],
                "score": hit["score"],
                "source": meta.get("source", ""),
                "confidence": meta.get("confidence", 0.5),
                "created_at": meta.get("created_at", "")[:10],
            }
            if type_ == "pattern" and meta.get("so_url"):
                entry["so_url"] = meta["so_url"]
            raw.append(entry)

    # Deduplicate by id, keep highest score
    seen: dict[str, dict] = {}
    for item in raw:
        if item["id"] not in seen or item["score"] > seen[item["id"]]["score"]:
            seen[item["id"]] = item

    suggestions = sorted(seen.values(), key=lambda x: -x["score"])[:top_k]

    return {
        "error": error,
        "project": project,
        "suggestions": suggestions,
        "count": len(suggestions),
    }

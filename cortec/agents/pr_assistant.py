"""
PR assistant — drafts a PR summary from project memory.

Pulls recent decisions, fixes, and bugs, then assembles a structured
PR description template the developer can paste into GitHub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage.db import MetadataStore
    from ..storage.vector import VectorStore


def draft(
    db: "MetadataStore",
    vector: "VectorStore",
    project: str,
    context: str = "",
    top_k: int = 8,
) -> dict:
    """
    Draft a PR summary for a project using its stored memories.

    Pulls the most recent decisions, fixes, and bugs, then optionally
    runs a semantic search against `context` to surface relevant memories.
    Returns a structured dict with `template` (ready-to-paste markdown)
    and grouped memory lists for each section.
    """
    memories = db.list_all(project=project, approved_only=True)

    decisions = [m for m in memories if m["type"] == "decision"]
    fixes = [m for m in memories if m["type"] == "fix"]
    bugs = [m for m in memories if m["type"] == "bug"]
    arch = [m for m in memories if m["type"] == "architecture"]

    relevant: list[dict] = []
    if context.strip() and vector.count() > 0:
        hits = vector.search(context, top_k=top_k, project=project)
        for hit in hits:
            meta = db.get(hit["id"])
            if meta:
                relevant.append({
                    "id": hit["id"],
                    "type": meta["type"],
                    "summary": hit["document"],
                    "score": hit["score"],
                })

    template = _build_template(project, context, decisions, fixes, bugs, arch, relevant)

    return {
        "project": project,
        "context": context,
        "template": template,
        "decisions": _trim(decisions, 5),
        "fixes": _trim(fixes, 5),
        "bugs": _trim(bugs, 5),
        "relevant": relevant[:5],
        "total_memories": len(memories),
    }


def _trim(memories: list[dict], n: int) -> list[dict]:
    """Return up to n memory dicts with id and truncated summary."""
    return [{"id": m["id"], "summary": m["summary"][:120]} for m in memories[:n]]


def _build_template(
    project: str,
    context: str,
    decisions: list[dict],
    fixes: list[dict],
    bugs: list[dict],
    arch: list[dict],
    relevant: list[dict],
) -> str:
    """Assemble a ready-to-paste GitHub PR description from memory sections."""
    lines: list[str] = []
    lines.append(f"## Summary\n")

    if context.strip():
        lines.append(f"{context.strip()}\n")

    if relevant:
        lines.append("**Relevant context from memory:**")
        for r in relevant[:3]:
            lines.append(f"- [{r['type']}] {r['summary'][:100]}")
        lines.append("")

    if decisions:
        lines.append("**Key decisions:**")
        for d in decisions[:3]:
            lines.append(f"- {d['summary'][:100]}")
        lines.append("")

    if fixes:
        lines.append("**Fixes included:**")
        for f in fixes[:3]:
            lines.append(f"- {f['summary'][:100]}")
        lines.append("")

    if bugs:
        lines.append("**Bugs addressed:**")
        for b in bugs[:3]:
            lines.append(f"- {b['summary'][:100]}")
        lines.append("")

    if arch:
        lines.append("**Architecture notes:**")
        for a in arch[:2]:
            lines.append(f"- {a['summary'][:100]}")
        lines.append("")

    lines.append("## Test plan\n")
    lines.append("- [ ] ...")
    lines.append("")
    lines.append(f"_Generated from {project} memory — {sum(map(bool, [decisions, fixes, bugs, arch]))} memory types referenced._")

    return "\n".join(lines)

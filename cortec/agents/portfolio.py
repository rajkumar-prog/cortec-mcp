"""
Portfolio builder — aggregates portfolio and resume memories into export-ready output.

Collects portfolio and resume type memories from the store and formats them
as structured entries with an optional Markdown export.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage.db import MetadataStore


def build(db: "MetadataStore", project: str | None = None) -> dict:
    """
    Aggregate portfolio and resume memories into a structured portfolio.

    Returns grouped entries for portfolio items, resume achievements, key
    decisions, and a ready-to-export Markdown string under `markdown`.
    """
    memories = db.list_all(project=project, approved_only=True)

    portfolio_items = [m for m in memories if m["type"] == "portfolio"]
    resume_items = [m for m in memories if m["type"] == "resume"]
    decision_items = [m for m in memories if m["type"] == "decision"]
    architecture_items = [m for m in memories if m["type"] == "architecture"]

    highlights = portfolio_items + resume_items

    return {
        "project": project or "all",
        "portfolio": _format(portfolio_items),
        "resume": _format(resume_items),
        "key_decisions": _format(decision_items[:5]),
        "architecture": _format(architecture_items[:5]),
        "total_memories": len(memories),
        "highlight_count": len(highlights),
        "markdown": _to_markdown(project, portfolio_items, resume_items, decision_items, architecture_items),
    }


def _format(memories: list[dict]) -> list[dict]:
    """Return a compact list of id, summary, and date for each memory."""
    return [
        {
            "id": m["id"],
            "summary": m["summary"],
            "created_at": m.get("created_at", "")[:10],
        }
        for m in memories
    ]


def _to_markdown(
    project: str | None,
    portfolio: list[dict],
    resume: list[dict],
    decisions: list[dict],
    architecture: list[dict],
) -> str:
    """Render a Markdown portfolio export from memory sections."""
    lines: list[str] = []
    title = f"Portfolio — {project}" if project else "Portfolio"
    lines.append(f"# {title}\n")

    if portfolio:
        lines.append("## Highlights\n")
        for m in portfolio:
            lines.append(f"- {m['summary']}  _{m.get('created_at', '')[:10]}_")
        lines.append("")

    if resume:
        lines.append("## Achievements\n")
        for m in resume:
            lines.append(f"- {m['summary']}  _{m.get('created_at', '')[:10]}_")
        lines.append("")

    if decisions:
        lines.append("## Key Technical Decisions\n")
        for m in decisions[:5]:
            lines.append(f"- {m['summary'][:120]}")
        lines.append("")

    if architecture:
        lines.append("## Architecture Notes\n")
        for m in architecture[:5]:
            lines.append(f"- {m['summary'][:120]}")
        lines.append("")

    if not any([portfolio, resume, decisions, architecture]):
        lines.append("_No portfolio, resume, decision, or architecture memories found._\n")
        lines.append("Store some with:\n")
        lines.append("```")
        lines.append('cortec remember "..." --type portfolio')
        lines.append('cortec remember "..." --type resume')
        lines.append("```")

    return "\n".join(lines)

"""
Agent workflows — PR review, debug assistant, and portfolio builder.

Each workflow queries the memory store for relevant context and returns
structured, actionable output powered by the developer's own history.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .storage.db import MetadataStore
from .storage.vector import VectorStore


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ReviewFinding:
    """A single finding from a PR review, backed by a recalled memory."""
    memory_id: str
    summary: str
    relevance_score: float
    memory_type: str
    confidence: float
    suggestion: str


@dataclass
class ReviewResult:
    """Complete PR review output."""
    findings: list[ReviewFinding] = field(default_factory=list)
    files_analyzed: list[str] = field(default_factory=list)
    memories_consulted: int = 0


@dataclass
class DebugSuggestion:
    """A single debug suggestion backed by a recalled memory."""
    memory_id: str
    summary: str
    relevance_score: float
    memory_type: str
    confidence: float
    source: str


@dataclass
class DebugResult:
    """Complete debug assistant output."""
    suggestions: list[DebugSuggestion] = field(default_factory=list)
    patterns: list[DebugSuggestion] = field(default_factory=list)
    memories_consulted: int = 0


@dataclass
class PortfolioEntry:
    """A single portfolio or resume entry."""
    memory_id: str
    summary: str
    memory_type: str
    project: str
    confidence: float
    created_at: str
    tags: list[str] = field(default_factory=list)


@dataclass
class PortfolioResult:
    """Complete portfolio builder output."""
    entries: list[PortfolioEntry] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    total: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────────

_DIFF_FILE_RE = re.compile(r"^(?:diff --git a/|[+]{3} b/)(.+)$", re.MULTILINE)


def extract_diff_files(diff: str) -> list[str]:
    """Pull file paths out of a unified diff."""
    return sorted(set(_DIFF_FILE_RE.findall(diff)))


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract meaningful keywords from text for search queries."""
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "just", "because", "but", "and",
        "or", "if", "while", "about", "up", "it", "its", "this", "that",
        "these", "those", "i", "you", "he", "she", "we", "they", "me",
        "him", "her", "us", "them", "my", "your", "his", "our", "their",
        "what", "which", "who", "whom", "whose",
        "diff", "git", "index", "file", "line", "add", "remove", "change",
    }
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        lower = w.lower()
        if lower not in stop and lower not in seen:
            seen.add(lower)
            keywords.append(w)
            if len(keywords) >= max_keywords:
                break
    return keywords


# ── PR Review Agent ──────────────────────────────────────────────────────────

_REVIEW_TYPES = ("decision", "architecture", "pattern", "bug", "fix", "preference", "dependency")

_SUGGESTION_MAP = {
    "decision":     "This change may relate to a previous decision — verify consistency.",
    "architecture": "Check that this aligns with the established architecture.",
    "pattern":      "A known pattern may apply here — consider reusing it.",
    "bug":          "A similar bug was encountered before — check if this reintroduces it.",
    "fix":          "A related fix exists in memory — verify this change doesn't conflict.",
    "preference":   "This may conflict with an established preference.",
    "dependency":   "Verify dependency compatibility with existing decisions.",
}


def review_pr(
    diff: str,
    db: MetadataStore,
    vector: VectorStore,
    project: str | None = None,
    top_k: int = 5,
) -> ReviewResult:
    """Review a PR diff against stored memories.

    Extracts files and keywords from the diff, searches for related memories,
    and returns findings that flag potential issues or relevant context.
    """
    if vector.count() == 0:
        return ReviewResult()

    files = extract_diff_files(diff)
    keywords = _extract_keywords(diff, max_keywords=12)
    query = " ".join(keywords) if keywords else diff[:500]

    seen_ids: set[str] = set()
    findings: list[ReviewFinding] = []

    for type_ in _REVIEW_TYPES:
        hits = vector.search(query=query, top_k=top_k, project=project, type_=type_)
        for hit in hits:
            if hit["id"] in seen_ids:
                continue
            seen_ids.add(hit["id"])
            meta = db.get(hit["id"])
            if not meta:
                continue
            findings.append(ReviewFinding(
                memory_id=hit["id"],
                summary=hit["document"],
                relevance_score=hit["score"],
                memory_type=meta["type"],
                confidence=meta["confidence"],
                suggestion=_SUGGESTION_MAP.get(meta["type"], "Review this memory for relevance."),
            ))

    findings.sort(key=lambda f: (-f.relevance_score, -f.confidence))

    return ReviewResult(
        findings=findings[:top_k * 2],
        files_analyzed=files,
        memories_consulted=len(seen_ids),
    )


# ── Debug Assistant ──────────────────────────────────────────────────────────

_DEBUG_TYPES = ("bug", "fix", "pattern", "command")


def debug_assist(
    error: str,
    db: MetadataStore,
    vector: VectorStore,
    project: str | None = None,
    top_k: int = 5,
) -> DebugResult:
    """Search memories for relevant bugs, fixes, and patterns that match an error.

    Returns suggestions (bugs/fixes) and patterns separately, sorted by
    relevance score and confidence.
    """
    if vector.count() == 0:
        return DebugResult()

    seen_ids: set[str] = set()
    suggestions: list[DebugSuggestion] = []
    patterns: list[DebugSuggestion] = []

    for type_ in _DEBUG_TYPES:
        hits = vector.search(query=error, top_k=top_k, project=project, type_=type_)
        for hit in hits:
            if hit["id"] in seen_ids:
                continue
            seen_ids.add(hit["id"])
            meta = db.get(hit["id"])
            if not meta:
                continue
            entry = DebugSuggestion(
                memory_id=hit["id"],
                summary=hit["document"],
                relevance_score=hit["score"],
                memory_type=meta["type"],
                confidence=meta["confidence"],
                source=meta.get("source", "unknown"),
            )
            if meta["type"] == "pattern":
                patterns.append(entry)
            else:
                suggestions.append(entry)

    suggestions.sort(key=lambda s: (-s.relevance_score, -s.confidence))
    patterns.sort(key=lambda s: (-s.relevance_score, -s.confidence))

    return DebugResult(
        suggestions=suggestions[:top_k],
        patterns=patterns[:top_k],
        memories_consulted=len(seen_ids),
    )


# ── Portfolio Builder ────────────────────────────────────────────────────────

_PORTFOLIO_TYPES = ("portfolio", "resume")


def build_portfolio(
    db: MetadataStore,
    project: str | None = None,
) -> PortfolioResult:
    """Build a portfolio from stored portfolio and resume memories.

    Collects all approved portfolio/resume memories, groups by project,
    and returns a structured result.
    """
    all_memories = db.list_all(project=project, approved_only=True)

    entries: list[PortfolioEntry] = []
    projects: set[str] = set()

    for m in all_memories:
        if m["type"] not in _PORTFOLIO_TYPES:
            continue
        projects.add(m["project"])
        entries.append(PortfolioEntry(
            memory_id=m["id"],
            summary=m["summary"],
            memory_type=m["type"],
            project=m["project"],
            confidence=m["confidence"],
            created_at=m["created_at"][:10],
            tags=json.loads(m.get("tags", "[]")),
        ))

    entries.sort(key=lambda e: (e.project, e.created_at))

    return PortfolioResult(
        entries=entries,
        projects=sorted(projects),
        total=len(entries),
    )


def render_portfolio_markdown(result: PortfolioResult) -> str:
    """Render a PortfolioResult as a Markdown document."""
    if not result.entries:
        return "# Portfolio\n\nNo portfolio or resume entries found.\n"

    lines = ["# Portfolio", ""]

    by_project: dict[str, list[PortfolioEntry]] = {}
    for e in result.entries:
        by_project.setdefault(e.project, []).append(e)

    for proj in sorted(by_project):
        lines.append(f"## {proj}")
        lines.append("")
        for e in by_project[proj]:
            tag_str = f"  [{', '.join(e.tags)}]" if e.tags else ""
            label = "Achievement" if e.memory_type == "resume" else "Project"
            lines.append(f"- **{label}**: {e.summary}{tag_str}")
        lines.append("")

    lines.append(f"---\n\n*{result.total} entries across {len(result.projects)} project(s)*\n")
    return "\n".join(lines)

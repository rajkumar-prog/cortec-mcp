"""
Conflict detection — identifies when new memories contradict existing ones.
Checks for contradictions within the same project and type.
"""

import re
from dataclasses import dataclass


@dataclass
class ConflictResult:
    found: bool
    existing_id: str | None
    description: str | None


# ── Contradiction signal pairs ────────────────────────────────────────────────
# Each tuple: (pattern_a, pattern_b, label)
# If one memory matches pattern_a and another matches pattern_b
# for the same key concept — it's a likely conflict.

_OPPOSITES: list[tuple[re.Pattern, re.Pattern, str]] = [
    (re.compile(r"\buse\b.{0,30}\bflask\b",    re.I), re.compile(r"\buse\b.{0,30}\bdjango\b",  re.I), "web framework"),
    (re.compile(r"\buse\b.{0,30}\bpostgres\b",  re.I), re.compile(r"\buse\b.{0,30}\bmysql\b",   re.I), "database"),
    (re.compile(r"\buse\b.{0,30}\bmysql\b",     re.I), re.compile(r"\buse\b.{0,30}\bsqlite\b",  re.I), "database"),
    (re.compile(r"\buse\b.{0,30}\bchroma\b",    re.I), re.compile(r"\buse\b.{0,30}\bqdrant\b",  re.I), "vector database"),
    (re.compile(r"\buse\b.{0,30}\bfastapi\b",   re.I), re.compile(r"\buse\b.{0,30}\bflask\b",   re.I), "web framework"),
    (re.compile(r"\buse\b.{0,30}\breact\b",     re.I), re.compile(r"\buse\b.{0,30}\bvue\b",     re.I), "frontend framework"),
    (re.compile(r"\buse\b.{0,30}\bpython\b",    re.I), re.compile(r"\buse\b.{0,30}\bnode\b",    re.I), "runtime"),
    (re.compile(r"\buse\b.{0,30}\bnpm\b",       re.I), re.compile(r"\buse\b.{0,30}\bpnpm\b",    re.I), "package manager"),
    (re.compile(r"\buse\b.{0,30}\bnpm\b",       re.I), re.compile(r"\buse\b.{0,30}\byarn\b",    re.I), "package manager"),
    (re.compile(r"\bdo\s+not\b.{0,40}",         re.I), re.compile(r"\balways\b.{0,40}",         re.I), "rule contradiction"),
    (re.compile(r"\bavoid\b.{0,30}",            re.I), re.compile(r"\bprefer\b.{0,30}",         re.I), "preference contradiction"),
]

# Shared concept extractor — finds tech names and choices in text
_TECH_PATTERN = re.compile(
    r"\b(flask|django|fastapi|postgres|postgresql|mysql|sqlite|mongodb|redis|"
    r"chroma|qdrant|pinecone|weaviate|react|vue|angular|svelte|next\.?js|nuxt|"
    r"python|node|nodejs|deno|bun|npm|yarn|pnpm|docker|kubernetes|"
    r"sqlite3|supabase|firebase|aws|gcp|azure)\b",
    re.I,
)


def _extract_tech(text: str) -> set[str]:
    return {m.lower() for m in _TECH_PATTERN.findall(text)}


def detect(
    new_text: str,
    existing_memories: list[dict],
    project: str,
    type_: str,
) -> ConflictResult:
    """
    Compare new_text against existing approved memories of the same project + type.
    Returns a ConflictResult describing any contradiction found.
    """
    same_type = [
        m for m in existing_memories
        if m.get("project") == project and m.get("type") == type_
    ]
    if not same_type:
        return ConflictResult(found=False, existing_id=None, description=None)

    new_techs = _extract_tech(new_text)

    for mem in same_type:
        existing_text = mem.get("summary", "")
        existing_techs = _extract_tech(existing_text)

        # Check opposite pattern pairs
        for pat_a, pat_b, label in _OPPOSITES:
            new_a = bool(pat_a.search(new_text))
            new_b = bool(pat_b.search(new_text))
            ex_a  = bool(pat_a.search(existing_text))
            ex_b  = bool(pat_b.search(existing_text))

            if (new_a and ex_b) or (new_b and ex_a):
                return ConflictResult(
                    found=True,
                    existing_id=mem["id"],
                    description=(
                        f"Possible {label} conflict detected.\n"
                        f"  Existing [{mem['id']}]: {existing_text[:100]}\n"
                        f"  New memory: {new_text[:100]}"
                    ),
                )

        # Check tech overlap contradiction
        # If both memories mention different tech in the same category — flag it
        conflict_techs = new_techs & existing_techs
        if not conflict_techs and new_techs and existing_techs:
            # Both have tech mentions but no overlap — possible contradiction
            overlap_check = new_techs.symmetric_difference(existing_techs)
            if len(overlap_check) >= 2 and type_ in ("decision", "architecture", "preference"):
                return ConflictResult(
                    found=True,
                    existing_id=mem["id"],
                    description=(
                        f"Possible technology conflict in '{type_}' memories.\n"
                        f"  Existing [{mem['id']}] mentions: {', '.join(existing_techs)}\n"
                        f"  New memory mentions: {', '.join(new_techs)}\n"
                        "  Please confirm which is correct."
                    ),
                )

    return ConflictResult(found=False, existing_id=None, description=None)

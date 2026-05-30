"""
Cortec configuration — paths, modes, and defaults.
"""

from pathlib import Path
from enum import Enum


# ── Approval modes ──────────────────────────────────────────────────────────

class ApprovalMode(str, Enum):
    AUTO             = "auto"             # store immediately, no prompt
    MANUAL           = "manual"           # user must call remember explicitly
    APPROVAL_REQUIRED = "approval_required"  # queue for review, then confirm


# ── Confidence scale (source-based) ─────────────────────────────────────────

class Confidence:
    USER_CONFIRMED   = 0.9
    GITHUB           = 0.8
    SESSION_SUMMARY  = 0.7
    STACKOVERFLOW    = 0.6
    INFERRED         = 0.5

    # Maps source names to confidence scores — checked in order, first match wins
    _SOURCE_MAP: list[tuple[tuple[str, ...], float]] = [
        (("confirmed", "user"),                                         0.9),
        (("github_commit", "github_pr", "github_issue", "github"),     0.8),
        (("session", "chat", "summary"),                                0.7),
        (("stackoverflow", "stack_overflow", "so_"),                    0.6),
    ]

    @staticmethod
    def from_source(source: str) -> float:
        s = source.lower()
        for keywords, score in Confidence._SOURCE_MAP:
            if any(k in s for k in keywords):
                return score
        return Confidence.INFERRED


# ── Memory types ─────────────────────────────────────────────────────────────

MEMORY_TYPES = {
    "decision":     "An explicit choice made about the project (tech, design, approach).",
    "bug":          "A bug or error encountered during development.",
    "fix":          "A solution or fix applied to a bug or problem.",
    "architecture": "A structural or design pattern decision.",
    "preference":   "A personal or team preference (style, tooling, workflow).",
    "command":      "A useful CLI command or script worth remembering.",
    "dependency":   "A library, package, or external dependency decision.",
    "portfolio":    "Something worth highlighting in a portfolio or showcase.",
    "resume":       "An achievement or skill worth adding to a resume.",
    "general":      "General note that does not fit other categories.",
}

VALID_TYPES = set(MEMORY_TYPES.keys())


def validate_type(type_: str) -> str:
    """Validate and return the memory type. Falls back to 'general' if unknown."""
    if type_ in VALID_TYPES:
        return type_
    raise ValueError(
        f"Invalid memory type '{type_}'. "
        f"Valid types: {', '.join(sorted(VALID_TYPES))}"
    )


# ── Paths ────────────────────────────────────────────────────────────────────

class CortecPaths:
    def __init__(self, base: Path | None = None):
        self.base     = base or Path.home() / ".cortec"
        self.db       = self.base / "cortec.db"
        self.chroma   = self.base / "chroma"
        self.archive  = self.base / "archive"
        self.pending  = self.base / "pending"

    def init(self):
        for d in [self.base, self.chroma, self.archive, self.pending]:
            d.mkdir(parents=True, exist_ok=True)


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_APPROVAL_MODE  = ApprovalMode.APPROVAL_REQUIRED
DEFAULT_PROJECT        = "default"
RECALL_TOP_K           = 5

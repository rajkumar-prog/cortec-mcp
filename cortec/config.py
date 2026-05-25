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

    @staticmethod
    def from_source(source: str) -> float:
        source = source.lower()
        if "github" in source or "commit" in source or "pr" in source:
            return Confidence.GITHUB
        if "session" in source or "chat" in source:
            return Confidence.SESSION_SUMMARY
        if "stackoverflow" in source or "so" in source:
            return Confidence.STACKOVERFLOW
        if "confirmed" in source or "user" in source:
            return Confidence.USER_CONFIRMED
        return Confidence.INFERRED


# ── Memory types ─────────────────────────────────────────────────────────────

MEMORY_TYPES = [
    "decision",
    "bug",
    "fix",
    "architecture",
    "preference",
    "command",
    "dependency",
    "portfolio",
    "resume",
    "general",
]


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

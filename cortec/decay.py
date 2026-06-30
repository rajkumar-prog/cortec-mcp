"""
Confidence decay — ages a memory's confidence toward a floor over time.

Decay is computed at read time from the stored confidence and created_at; the
stored value is never mutated. A memory's confidence at creation is treated as
immutable provenance, and staleness is a lens applied on top of it.

Formula (half-life decay toward a floor):

    effective = floor + (base - floor) * 0.5 ** (age_days / half_life)

At age 0 the effective confidence equals the base; it halves the remaining gap
to the floor every `half_life` days and asymptotes to the floor.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import (
    DECAY_FLOOR,
    DECAY_HALF_LIFE_DAYS,
    DEFAULT_HALF_LIFE,
    STALE_THRESHOLD,
)


def _parse_timestamp(created_at: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp into a tz-aware datetime, or None if unparseable."""
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def age_days(created_at: str | None, now: datetime | None = None) -> float:
    """Return the age of a memory in days. Unparseable or future timestamps give 0."""
    dt = _parse_timestamp(created_at)
    if dt is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    delta = (now - dt).total_seconds() / 86400.0
    return max(0.0, delta)


def half_life_for(type_: str) -> int:
    """Return the decay half-life in days for a memory type."""
    return DECAY_HALF_LIFE_DAYS.get(type_, DEFAULT_HALF_LIFE)


def effective_confidence(
    base: float,
    created_at: str | None,
    type_: str = "general",
    now: datetime | None = None,
    floor: float = DECAY_FLOOR,
) -> float:
    """
    Return the age-decayed confidence for a memory.

    Decays the base confidence toward `floor` with a per-type half-life. A base
    already at or below the floor is returned unchanged.
    """
    if base <= floor:
        return round(base, 4)
    age = age_days(created_at, now=now)
    half_life = half_life_for(type_)
    decayed = floor + (base - floor) * (0.5 ** (age / half_life))
    return round(decayed, 4)


def is_stale(
    base: float,
    created_at: str | None,
    type_: str = "general",
    now: datetime | None = None,
    threshold: float = STALE_THRESHOLD,
) -> bool:
    """Return True if the memory's effective confidence has decayed below the threshold."""
    return effective_confidence(base, created_at, type_, now=now) < threshold


def annotate(memory: dict, now: datetime | None = None) -> dict:
    """
    Return a copy of a memory dict enriched with decay fields.

    Adds `effective_confidence`, `age_days`, and `stale` without touching the
    stored `confidence`. Leaves the original dict unmodified.
    """
    now = now or datetime.now(timezone.utc)
    base = memory.get("confidence", DECAY_FLOOR)
    created = memory.get("created_at")
    type_ = memory.get("type", "general")

    eff = effective_confidence(base, created, type_, now=now)
    enriched = dict(memory)
    enriched["effective_confidence"] = eff
    enriched["age_days"] = round(age_days(created, now=now), 1)
    enriched["stale"] = eff < STALE_THRESHOLD
    return enriched

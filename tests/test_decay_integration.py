"""Integration tests — decay applied to memories stored in a real SQLite store."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cortec import decay
from cortec.config import STALE_THRESHOLD
from cortec.storage.db import MetadataStore


def _store() -> MetadataStore:
    tmp = tempfile.mkdtemp()
    return MetadataStore(Path(tmp) / "test.db")


def _backdate(db: MetadataStore, memory_id: str, days: float) -> None:
    """Rewrite a memory's created_at to `days` in the past."""
    past = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db._conn() as conn:
        conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", (past, memory_id))


def test_fresh_memory_not_flagged_stale():
    db = _store()
    mid = db.insert(summary="recent fix", type_="fix", confidence=0.8, approved=True)
    m = db.get(mid)
    assert not decay.annotate(m)["stale"]


def test_old_bug_flagged_stale():
    db = _store()
    mid = db.insert(summary="ancient bug", type_="bug", confidence=0.7, approved=True)
    _backdate(db, mid, 400)
    m = db.get(mid)
    annotated = decay.annotate(m)
    assert annotated["stale"]
    assert annotated["effective_confidence"] < STALE_THRESHOLD


def test_old_architecture_survives():
    db = _store()
    mid = db.insert(summary="hexagonal core", type_="architecture", confidence=0.9, approved=True)
    _backdate(db, mid, 400)
    m = db.get(mid)
    # architecture half-life is long, so it should stay above the stale threshold
    assert not decay.annotate(m)["stale"]


def test_stale_filter_across_store():
    db = _store()
    fresh = db.insert(summary="fresh decision", type_="decision", confidence=0.9, approved=True)
    old_bug = db.insert(summary="old bug", type_="bug", confidence=0.6, approved=True)
    _backdate(db, old_bug, 500)

    memories = db.list_all(approved_only=True)
    stale = [decay.annotate(m) for m in memories]
    stale_ids = {m["id"] for m in stale if m["stale"]}

    assert old_bug in stale_ids
    assert fresh not in stale_ids


def test_effective_confidence_lower_than_stored_for_aged_memory():
    db = _store()
    mid = db.insert(summary="aging note", type_="general", confidence=0.8, approved=True)
    _backdate(db, mid, 200)
    m = db.get(mid)
    annotated = decay.annotate(m)
    assert annotated["effective_confidence"] < m["confidence"]
    assert annotated["age_days"] >= 199

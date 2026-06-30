"""Tests for cortec.decay — age-based confidence decay."""

from datetime import datetime, timedelta, timezone

import pytest

from cortec import decay
from cortec.config import DECAY_FLOOR, STALE_THRESHOLD, DEFAULT_HALF_LIFE


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ago(days: float) -> str:
    """ISO timestamp for `days` before the fixed NOW."""
    return (NOW - timedelta(days=days)).isoformat()


# ── age_days ──────────────────────────────────────────────────────────────────

def test_age_days_zero_for_now():
    assert decay.age_days(NOW.isoformat(), now=NOW) == pytest.approx(0.0)


def test_age_days_counts_days():
    assert decay.age_days(_ago(30), now=NOW) == pytest.approx(30.0)


def test_age_days_future_clamps_to_zero():
    future = (NOW + timedelta(days=10)).isoformat()
    assert decay.age_days(future, now=NOW) == 0.0


def test_age_days_none():
    assert decay.age_days(None, now=NOW) == 0.0


def test_age_days_garbage():
    assert decay.age_days("not-a-date", now=NOW) == 0.0


def test_age_days_naive_timestamp_treated_as_utc():
    naive = (NOW - timedelta(days=5)).replace(tzinfo=None).isoformat()
    assert decay.age_days(naive, now=NOW) == pytest.approx(5.0)


# ── effective_confidence ────────────────────────────────────────────────────────

def test_effective_equals_base_at_age_zero():
    assert decay.effective_confidence(0.8, NOW.isoformat(), "general", now=NOW) == pytest.approx(0.8)


def test_effective_halves_gap_at_one_half_life():
    # general half-life = 120 days; base 0.9, floor 0.1 → midpoint 0.5
    eff = decay.effective_confidence(0.9, _ago(DEFAULT_HALF_LIFE), "general", now=NOW)
    assert eff == pytest.approx(0.5, abs=1e-3)


def test_effective_approaches_floor_when_old():
    eff = decay.effective_confidence(0.9, _ago(10000), "general", now=NOW)
    assert eff == pytest.approx(DECAY_FLOOR, abs=1e-2)


def test_effective_never_below_floor():
    eff = decay.effective_confidence(0.9, _ago(100000), "bug", now=NOW)
    assert eff >= DECAY_FLOOR


def test_effective_monotonic_decreasing_with_age():
    young = decay.effective_confidence(0.8, _ago(10), "fix", now=NOW)
    old = decay.effective_confidence(0.8, _ago(200), "fix", now=NOW)
    assert young > old


def test_base_at_floor_returned_unchanged():
    assert decay.effective_confidence(DECAY_FLOOR, _ago(500), "general", now=NOW) == DECAY_FLOOR


def test_base_below_floor_returned_unchanged():
    assert decay.effective_confidence(0.05, _ago(500), "general", now=NOW) == 0.05


def test_architecture_decays_slower_than_bug():
    arch = decay.effective_confidence(0.8, _ago(90), "architecture", now=NOW)
    bug = decay.effective_confidence(0.8, _ago(90), "bug", now=NOW)
    assert arch > bug


def test_unknown_type_uses_default_half_life():
    known = decay.effective_confidence(0.8, _ago(60), "general", now=NOW)
    unknown = decay.effective_confidence(0.8, _ago(60), "made-up-type", now=NOW)
    assert known == pytest.approx(unknown)


# ── is_stale ─────────────────────────────────────────────────────────────────

def test_fresh_memory_not_stale():
    assert not decay.is_stale(0.8, NOW.isoformat(), "general", now=NOW)


def test_old_volatile_memory_is_stale():
    # bug half-life = 60; after a long time it drops below the stale threshold
    assert decay.is_stale(0.7, _ago(365), "bug", now=NOW)


def test_stale_respects_custom_threshold():
    # With a very low threshold, even an old memory is not stale
    assert not decay.is_stale(0.7, _ago(365), "bug", now=NOW, threshold=0.05)


# ── annotate ─────────────────────────────────────────────────────────────────

def test_annotate_adds_fields():
    mem = {"confidence": 0.8, "created_at": _ago(30), "type": "fix", "id": "a1"}
    out = decay.annotate(mem, now=NOW)
    assert "effective_confidence" in out
    assert "age_days" in out
    assert "stale" in out
    assert out["age_days"] == pytest.approx(30.0)


def test_annotate_does_not_mutate_original():
    mem = {"confidence": 0.8, "created_at": _ago(30), "type": "fix"}
    decay.annotate(mem, now=NOW)
    assert "effective_confidence" not in mem
    assert mem["confidence"] == 0.8


def test_annotate_preserves_existing_fields():
    mem = {"confidence": 0.8, "created_at": _ago(5), "type": "decision", "summary": "x", "id": "z9"}
    out = decay.annotate(mem, now=NOW)
    assert out["summary"] == "x"
    assert out["id"] == "z9"


def test_annotate_handles_missing_confidence():
    mem = {"created_at": _ago(5), "type": "general"}
    out = decay.annotate(mem, now=NOW)
    # falls back to floor, which is returned unchanged
    assert out["effective_confidence"] == DECAY_FLOOR

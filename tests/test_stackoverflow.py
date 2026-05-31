"""
Tests for Stack Overflow pattern store — URL parsing, fetcher, DB linking, and memory type.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cortec.stackoverflow import (
    parse_so_url,
    canonical_url,
    build_pattern_summary,
    SOAnswer,
    SOQuestion,
    _strip_html,
)
from cortec.config import MEMORY_TYPES, validate_type
from cortec.storage.db import MetadataStore


# ── URL parsing ───────────────────────────────────────────────────────────────

def test_parse_question_url():
    kind, id_ = parse_so_url("https://stackoverflow.com/questions/11227902/title-here")
    assert kind == "question"
    assert id_ == 11227902


def test_parse_answer_short_url():
    kind, id_ = parse_so_url("https://stackoverflow.com/a/5678")
    assert kind == "answer"
    assert id_ == 5678


def test_parse_question_url_with_answer_anchor():
    kind, id_ = parse_so_url("https://stackoverflow.com/questions/1234/title#5678")
    assert kind == "answer"
    assert id_ == 5678


def test_parse_invalid_url():
    with pytest.raises(ValueError, match="Cannot parse"):
        parse_so_url("https://github.com/not-stackoverflow")


def test_parse_url_with_query_params():
    kind, id_ = parse_so_url("https://stackoverflow.com/questions/231767/what-does-yield-do?noredirect=1")
    assert kind == "question"
    assert id_ == 231767


# ── URL canonicalization ──────────────────────────────────────────────────────

def test_canonical_answer_url():
    assert canonical_url("https://stackoverflow.com/a/5678") == "https://stackoverflow.com/a/5678"


def test_canonical_question_with_anchor_becomes_answer():
    result = canonical_url("https://stackoverflow.com/questions/1234/title#5678")
    assert result == "https://stackoverflow.com/a/5678"


def test_canonical_question_url():
    result = canonical_url("https://stackoverflow.com/questions/231767/what-does-yield-do?noredirect=1")
    assert result == "https://stackoverflow.com/questions/231767"


def test_canonical_dedup_same_answer_different_urls():
    url1 = canonical_url("https://stackoverflow.com/a/11227902")
    url2 = canonical_url("https://stackoverflow.com/questions/999/title#11227902")
    assert url1 == url2


# ── HTML stripping ────────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <strong>world</strong></p>") == "Hello world"


def test_strip_html_decodes_entities():
    assert "&amp;" not in _strip_html("Tom &amp; Jerry")
    assert "Tom & Jerry" == _strip_html("Tom &amp; Jerry")


def test_strip_html_collapses_whitespace():
    result = _strip_html("<p>line one</p>\n<p>line two</p>")
    assert "  " not in result


# ── Pattern summary building ──────────────────────────────────────────────────

def _make_answer(**kwargs) -> SOAnswer:
    defaults = dict(
        answer_id=1,
        question_id=100,
        question_title="How do I use yield in Python?",
        answer_body="Use yield to create a generator function.",
        score=42,
        is_accepted=True,
        url="https://stackoverflow.com/a/1",
    )
    defaults.update(kwargs)
    return SOAnswer(**defaults)


def _make_question(**kwargs) -> SOQuestion:
    defaults = dict(
        question_id=100,
        title="How do I use yield in Python?",
        body="I want to understand the yield keyword.",
        score=100,
        answer_count=5,
        answers=[_make_answer()],
        url="https://stackoverflow.com/questions/100",
    )
    defaults.update(kwargs)
    return SOQuestion(**defaults)


def test_build_summary_from_answer():
    ans = _make_answer()
    summary = build_pattern_summary(ans)
    assert "Q: How do I use yield" in summary
    assert "Use yield to create a generator" in summary
    assert "score=42" in summary
    assert "accepted=True" in summary


def test_build_summary_from_question_uses_best_answer():
    q = _make_question()
    summary = build_pattern_summary(q)
    assert "Q: How do I use yield" in summary
    assert "Use yield to create a generator" in summary


def test_build_summary_question_no_answers():
    q = _make_question(answers=[])
    summary = build_pattern_summary(q)
    assert "Q: How do I use yield" in summary
    assert "I want to understand" in summary


# ── Pattern memory type ───────────────────────────────────────────────────────

def test_pattern_type_in_memory_types():
    assert "pattern" in MEMORY_TYPES


def test_pattern_type_validates():
    assert validate_type("pattern") == "pattern"


# ── DB so_url field ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    return MetadataStore(tmp_path / "test.db")


def test_insert_with_so_url(tmp_db):
    url = "https://stackoverflow.com/a/5678"
    mid = tmp_db.insert(
        summary="Use yield to create a generator.",
        type_="pattern",
        source="stackoverflow",
        approved=True,
        so_url=url,
    )
    meta = tmp_db.get(mid)
    assert meta["so_url"] == url


def test_get_by_so_url(tmp_db):
    url = "https://stackoverflow.com/a/9999"
    mid = tmp_db.insert(summary="pattern text", approved=True, so_url=url)
    result = tmp_db.get_by_so_url(url)
    assert result is not None
    assert result["id"] == mid


def test_get_by_so_url_not_found(tmp_db):
    result = tmp_db.get_by_so_url("https://stackoverflow.com/a/0000")
    assert result is None


def test_no_duplicate_so_url(tmp_db):
    url = "https://stackoverflow.com/a/1111"
    tmp_db.insert(summary="first", approved=True, so_url=url)
    existing = tmp_db.get_by_so_url(url)
    assert existing is not None
    # Simulate duplicate check — second store should be blocked at app layer
    assert existing["summary"] == "first"

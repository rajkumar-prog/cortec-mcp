"""Tests for cortec.browse — filter, paginate, command parsing, and state transitions."""

import pytest

from cortec import browse
from cortec.browse import BrowseState


def _mem(id_, type_="general", project="proj", summary="a summary"):
    return {"id": id_, "type": type_, "project": project, "summary": summary}


def _many(n, type_="general", project="proj"):
    return [_mem(f"id{i:02d}", type_=type_, project=project, summary=f"memory {i}") for i in range(n)]


# ── apply_filters ──────────────────────────────────────────────────────────────

def test_filter_none_returns_all():
    mems = _many(5)
    assert browse.apply_filters(mems) == mems


def test_filter_by_project():
    mems = [_mem("a", project="x"), _mem("b", project="y")]
    out = browse.apply_filters(mems, project="x")
    assert [m["id"] for m in out] == ["a"]


def test_filter_by_type():
    mems = [_mem("a", type_="bug"), _mem("b", type_="fix")]
    out = browse.apply_filters(mems, type_="fix")
    assert [m["id"] for m in out] == ["b"]


def test_filter_by_query_case_insensitive():
    mems = [_mem("a", summary="Fixed AUTH bug"), _mem("b", summary="unrelated")]
    out = browse.apply_filters(mems, query="auth")
    assert [m["id"] for m in out] == ["a"]


def test_filter_query_handles_missing_summary():
    mems = [{"id": "a", "type": "general", "project": "p"}]  # no summary key
    assert browse.apply_filters(mems, query="x") == []


def test_filters_compose():
    mems = [
        _mem("a", type_="bug", project="x", summary="login crash"),
        _mem("b", type_="bug", project="x", summary="logout crash"),
        _mem("c", type_="fix", project="x", summary="login crash"),
    ]
    out = browse.apply_filters(mems, project="x", type_="bug", query="login")
    assert [m["id"] for m in out] == ["a"]


# ── paginate ─────────────────────────────────────────────────────────────────

def test_paginate_first_page():
    items = _many(25)
    page_items, total_pages, page = browse.paginate(items, 0, page_size=10)
    assert len(page_items) == 10
    assert total_pages == 3
    assert page == 0
    assert page_items[0]["id"] == "id00"


def test_paginate_last_partial_page():
    items = _many(25)
    page_items, total_pages, page = browse.paginate(items, 2, page_size=10)
    assert len(page_items) == 5
    assert page == 2


def test_paginate_clamps_overflow():
    items = _many(25)
    page_items, total_pages, page = browse.paginate(items, 99, page_size=10)
    assert page == 2  # clamped to last page


def test_paginate_clamps_negative():
    items = _many(5)
    _, _, page = browse.paginate(items, -5, page_size=10)
    assert page == 0


def test_paginate_empty():
    page_items, total_pages, page = browse.paginate([], 0, page_size=10)
    assert page_items == []
    assert total_pages == 1
    assert page == 0


def test_paginate_page_size_floor():
    # page_size <= 0 is treated as 1, never a ZeroDivisionError
    page_items, total_pages, _ = browse.paginate(_many(3), 0, page_size=0)
    assert len(page_items) == 1
    assert total_pages == 3


# ── parse_command ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("next", ("next", "")),
    ("n", ("next", "")),
    ("p", ("prev", "")),
    ("q", ("quit", "")),
    ("type bug", ("type", "bug")),
    ("t fix", ("type", "fix")),
    ("search login crash", ("search", "login crash")),
    ("s  trimmed  ", ("search", "trimmed")),
    ("open a1b2", ("open", "a1b2")),
    ("f a1b2", ("forget", "a1b2")),
    ("page 3", ("page", "3")),
    ("?", ("help", "")),
    ("", ("noop", "")),
    ("   ", ("noop", "")),
    ("bogus thing", ("unknown", "bogus thing")),
])
def test_parse_command(raw, expected):
    assert browse.parse_command(raw) == expected


def test_parse_command_none():
    assert browse.parse_command(None) == ("noop", "")


def test_parse_command_case_insensitive():
    assert browse.parse_command("NEXT") == ("next", "")
    assert browse.parse_command("Type Bug") == ("type", "Bug")


# ── step (state transitions) ─────────────────────────────────────────────────

def test_step_type_sets_and_resets_page():
    state = BrowseState(page=4)
    new, msg = browse.step(state, "type", "bug")
    assert new.type == "bug"
    assert new.page == 0
    assert "bug" in msg


def test_step_type_empty_clears():
    new, _ = browse.step(BrowseState(type="bug"), "type", "")
    assert new.type is None


def test_step_project_and_search():
    s1, _ = browse.step(BrowseState(), "project", "myapp")
    assert s1.project == "myapp"
    s2, _ = browse.step(s1, "search", "token")
    assert s2.query == "token"
    assert s2.project == "myapp"  # preserved


def test_step_clear_resets_everything():
    state = BrowseState(project="x", type="bug", query="q", page=3)
    new, _ = browse.step(state, "clear", "")
    assert new == BrowseState()


def test_step_next_prev():
    s = BrowseState(page=0)
    s, _ = browse.step(s, "next", "")
    assert s.page == 1
    s, _ = browse.step(s, "prev", "")
    assert s.page == 0
    s, _ = browse.step(s, "prev", "")
    assert s.page == 0  # never negative


def test_step_page_valid():
    new, _ = browse.step(BrowseState(), "page", "4")
    assert new.page == 3  # 1-indexed input -> 0-indexed


def test_step_page_invalid():
    state = BrowseState(page=2)
    new, msg = browse.step(state, "page", "abc")
    assert new.page == 2  # unchanged
    assert "invalid" in msg.lower()


def test_step_is_pure():
    state = BrowseState(project="x", page=1)
    browse.step(state, "next", "")
    assert state.project == "x" and state.page == 1  # original untouched (frozen)


# ── visible (integration of filter + paginate) ───────────────────────────────

def test_visible_reports_filtered_total():
    mems = _many(12, type_="bug") + _many(8, type_="fix")
    state = BrowseState(type="bug")
    page_items, total_pages, page, total = browse.visible(state, mems, page_size=10)
    assert total == 12
    assert total_pages == 2
    assert len(page_items) == 10


def test_visible_second_page():
    mems = _many(12, type_="bug")
    state = BrowseState(type="bug", page=1)
    page_items, total_pages, page, total = browse.visible(state, mems, page_size=10)
    assert len(page_items) == 2
    assert page == 1


# ── clamp_page (post-deletion safety) ────────────────────────────────────────

def test_clamp_page_pulls_back_after_shrink():
    # 12 items over 2 pages (size 10); on page 2, then collection shrinks to 10
    state = BrowseState(page=1)
    shrunk = _many(10)  # now only 1 page
    clamped = browse.clamp_page(state, shrunk, page_size=10)
    assert clamped.page == 0


def test_clamp_page_keeps_valid_page():
    state = BrowseState(page=1)
    mems = _many(25)  # 3 pages, page 1 still valid
    assert browse.clamp_page(state, mems, page_size=10).page == 1


def test_clamp_page_empty_collection():
    state = BrowseState(page=3)
    assert browse.clamp_page(state, [], page_size=10).page == 0


def test_clamp_page_respects_filters():
    # page 1 valid only if filtered set is large enough
    mems = _many(5, type_="bug") + _many(20, type_="fix")
    state = BrowseState(type="bug", page=1)  # only 5 bugs → 1 page
    assert browse.clamp_page(state, mems, page_size=10).page == 0


def test_clamp_page_is_pure():
    state = BrowseState(page=5)
    browse.clamp_page(state, _many(3), page_size=10)
    assert state.page == 5  # original frozen state untouched

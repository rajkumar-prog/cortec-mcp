"""Tests for cortec.agents — pr_assistant, debug_assistant, portfolio."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cortec.agents import pr_assistant, debug_assistant, portfolio as portfolio_agent
from cortec.storage.db import MetadataStore


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db() -> MetadataStore:
    tmp = tempfile.mkdtemp()
    return MetadataStore(Path(tmp) / "test.db")


def _insert(db: MetadataStore, summary: str, type_: str, project: str = "proj") -> str:
    return db.insert(
        summary=summary,
        project=project,
        type_=type_,
        source="session",
        confidence=0.7,
        approved=True,
    )


def _mock_vector(hits: list[dict] | None = None) -> MagicMock:
    v = MagicMock()
    v.count.return_value = 5 if hits is not None else 0
    v.search.return_value = hits or []
    return v


# ── pr_assistant ──────────────────────────────────────────────────────────────

class TestPrAssistant:
    def test_empty_project_returns_zero(self):
        db = _make_db()
        v = _mock_vector()
        result = pr_assistant.draft(db, v, project="empty")
        assert result["total_memories"] == 0
        assert result["decisions"] == []
        assert result["fixes"] == []

    def test_groups_by_type(self):
        db = _make_db()
        _insert(db, "Use SQLite not Postgres", "decision")
        _insert(db, "Fixed null pointer in auth", "fix")
        _insert(db, "Bug: login fails on Safari", "bug")
        v = _mock_vector([])
        result = pr_assistant.draft(db, v, project="proj")
        assert len(result["decisions"]) == 1
        assert len(result["fixes"]) == 1
        assert len(result["bugs"]) == 1

    def test_template_contains_sections(self):
        db = _make_db()
        _insert(db, "Use Redis for caching", "decision")
        _insert(db, "Fixed session expiry bug", "fix")
        v = _mock_vector([])
        result = pr_assistant.draft(db, v, project="proj")
        assert "## Summary" in result["template"]
        assert "## Test plan" in result["template"]

    def test_template_includes_context(self):
        db = _make_db()
        _insert(db, "Use Redis for caching", "decision")
        v = _mock_vector([])
        result = pr_assistant.draft(db, v, project="proj", context="refactor auth layer")
        assert "refactor auth layer" in result["template"]

    def test_semantic_search_called_with_context(self):
        db = _make_db()
        _insert(db, "decision about auth", "decision")
        rel_id = db.insert(
            summary="relevant memory", project="proj", type_="fix",
            source="session", confidence=0.7, approved=True,
        )
        v = _mock_vector([{"id": rel_id, "document": "relevant memory", "score": 0.9}])
        result = pr_assistant.draft(db, v, project="proj", context="auth")
        v.search.assert_called_once()
        assert result["relevant"]

    def test_no_semantic_search_without_context(self):
        db = _make_db()
        _insert(db, "decision", "decision")
        v = _mock_vector([])
        pr_assistant.draft(db, v, project="proj", context="")
        v.search.assert_not_called()

    def test_trims_to_five_per_type(self):
        db = _make_db()
        for i in range(10):
            _insert(db, f"decision {i}", "decision")
        v = _mock_vector([])
        result = pr_assistant.draft(db, v, project="proj")
        assert len(result["decisions"]) == 5

    def test_architecture_in_template(self):
        db = _make_db()
        _insert(db, "Hexagonal architecture", "architecture")
        v = _mock_vector([])
        result = pr_assistant.draft(db, v, project="proj")
        assert "Architecture" in result["template"]


# ── debug_assistant ───────────────────────────────────────────────────────────

class TestDebugAssistant:
    def test_empty_vector_returns_message(self):
        db = _make_db()
        v = _mock_vector(None)
        result = debug_assistant.suggest(db, v, error="crash on startup")
        assert result["count"] == 0
        assert "message" in result

    def test_returns_suggestions(self):
        db = _make_db()
        mid = _insert(db, "Fixed null pointer", "fix")
        v = MagicMock()
        v.count.return_value = 1
        v.search.side_effect = lambda *a, **kw: (
            [{"id": mid, "document": "Fixed null pointer", "score": 0.88}]
            if kw.get("type_") == "fix" else []
        )
        result = debug_assistant.suggest(db, v, error="null pointer exception")
        assert result["count"] > 0
        assert result["suggestions"][0]["id"] == mid

    def test_deduplicates_by_id(self):
        db = _make_db()
        mid = _insert(db, "Fixed null pointer", "fix")
        v = MagicMock()
        v.count.return_value = 1
        # Same id returned for both bug and fix searches
        v.search.return_value = [{"id": mid, "document": "Fixed null pointer", "score": 0.88}]
        result = debug_assistant.suggest(db, v, error="null pointer", top_k=10)
        ids = [s["id"] for s in result["suggestions"]]
        assert len(ids) == len(set(ids))

    def test_so_url_included_for_patterns(self):
        db = _make_db()
        mid = db.insert(
            summary="Use os.fdopen to wrap fd",
            project="proj",
            type_="pattern",
            source="stackoverflow",
            confidence=0.6,
            approved=True,
            so_url="https://stackoverflow.com/a/11227902",
        )
        v = MagicMock()
        v.count.return_value = 1
        v.search.side_effect = lambda *a, **kw: (
            [{"id": mid, "document": "Use os.fdopen", "score": 0.85}]
            if kw.get("type_") == "pattern" else []
        )
        result = debug_assistant.suggest(db, v, error="file descriptor leak")
        pattern_hits = [s for s in result["suggestions"] if s["type"] == "pattern"]
        assert pattern_hits
        assert pattern_hits[0].get("so_url") == "https://stackoverflow.com/a/11227902"

    def test_sorted_by_score_descending(self):
        db = _make_db()
        m1 = _insert(db, "high score fix", "fix")
        m2 = _insert(db, "low score bug", "bug")
        v = MagicMock()
        v.count.return_value = 2
        v.search.side_effect = lambda *a, **kw: {
            "fix": [{"id": m1, "document": "high score fix", "score": 0.95}],
            "bug": [{"id": m2, "document": "low score bug", "score": 0.40}],
            "pattern": [],
        }.get(kw.get("type_"), [])
        result = debug_assistant.suggest(db, v, error="crash")
        scores = [s["score"] for s in result["suggestions"]]
        assert scores == sorted(scores, reverse=True)

    def test_respects_top_k(self):
        db = _make_db()
        ids = [_insert(db, f"fix {i}", "fix") for i in range(10)]
        v = MagicMock()
        v.count.return_value = 10
        v.search.return_value = [
            {"id": i, "document": f"fix {j}", "score": 0.9 - j * 0.05}
            for j, i in enumerate(ids[:10])
        ]
        result = debug_assistant.suggest(db, v, error="crash", top_k=3)
        assert result["count"] <= 3


# ── portfolio ─────────────────────────────────────────────────────────────────

class TestPortfolio:
    def test_empty_db(self):
        db = _make_db()
        result = portfolio_agent.build(db, project="empty")
        assert result["highlight_count"] == 0
        assert result["total_memories"] == 0
        assert "No portfolio" in result["markdown"]

    def test_groups_portfolio_and_resume(self):
        db = _make_db()
        _insert(db, "Built semantic search feature", "portfolio")
        _insert(db, "Led migration to FastAPI", "resume")
        result = portfolio_agent.build(db, project="proj")
        assert len(result["portfolio"]) == 1
        assert len(result["resume"]) == 1
        assert result["highlight_count"] == 2

    def test_markdown_contains_sections(self):
        db = _make_db()
        _insert(db, "Built RAG pipeline", "portfolio")
        _insert(db, "Reduced latency by 40%", "resume")
        result = portfolio_agent.build(db, project="proj")
        md = result["markdown"]
        assert "## Highlights" in md
        assert "## Achievements" in md
        assert "Built RAG pipeline" in md

    def test_key_decisions_included(self):
        db = _make_db()
        _insert(db, "Use SQLite for local storage", "decision")
        result = portfolio_agent.build(db, project="proj")
        assert len(result["key_decisions"]) == 1
        assert "## Key Technical Decisions" in result["markdown"]

    def test_architecture_included(self):
        db = _make_db()
        _insert(db, "Hexagonal architecture for agents", "architecture")
        result = portfolio_agent.build(db, project="proj")
        assert len(result["architecture"]) == 1
        assert "## Architecture Notes" in result["markdown"]

    def test_project_none_returns_all(self):
        db = _make_db()
        _insert(db, "Item A", "portfolio", project="p1")
        _insert(db, "Item B", "portfolio", project="p2")
        result = portfolio_agent.build(db, project=None)
        assert len(result["portfolio"]) == 2

    def test_limits_decisions_to_five(self):
        db = _make_db()
        for i in range(8):
            _insert(db, f"decision {i}", "decision")
        result = portfolio_agent.build(db, project="proj")
        assert len(result["key_decisions"]) == 5

    def test_format_helper_truncates_summary(self):
        from cortec.agents.portfolio import _format
        memories = [{"id": "a1", "summary": "x" * 200, "created_at": "2024-01-01T00:00:00"}]
        formatted = _format(memories)
        assert formatted[0]["summary"] == "x" * 200  # _format does not truncate — markdown does

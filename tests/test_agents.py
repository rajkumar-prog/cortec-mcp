"""
Tests for Phase 6 agent workflows — PR review, debug assistant, and portfolio builder.
"""

import json
from pathlib import Path

import pytest

from cortec.agents import (
    review_pr,
    debug_assist,
    build_portfolio,
    render_portfolio_markdown,
    extract_diff_files,
    _extract_keywords,
    ReviewResult,
    DebugResult,
    PortfolioResult,
)
from cortec.storage.db import MetadataStore
from cortec.storage.vector import VectorStore


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    return MetadataStore(tmp_path / "test.db")


@pytest.fixture
def tmp_vector(tmp_path):
    return VectorStore(tmp_path / "chroma")


@pytest.fixture
def seeded_stores(tmp_db, tmp_vector):
    """Seed the stores with a variety of memory types for testing."""
    memories = [
        ("We use Chroma for vector storage — simpler local setup than Qdrant.", "decision", "cortec", 0.9),
        ("Bug: Chroma search fails on empty collection with IndexError.", "bug", "cortec", 0.7),
        ("Fix: Guard vector.search with count() > 0 check before querying.", "fix", "cortec", 0.7),
        ("Architecture: All MCP tools go through redact → scan → store pipeline.", "architecture", "cortec", 0.9),
        ("Pattern: Use contextmanager for SQLite connections to auto-commit.", "pattern", "cortec", 0.6),
        ("Built a local-first memory server with semantic search.", "portfolio", "cortec", 0.9),
        ("Implemented conflict detection engine with 15 regex patterns.", "resume", "cortec", 0.9),
        ("Prefer pytest over unittest for all test files.", "preference", "cortec", 0.7),
        ("pip install cortec-mcp", "command", "cortec", 0.7),
        ("Using httpx for async HTTP requests.", "dependency", "cortec", 0.8),
        ("Designed a REST API with FastAPI and PostgreSQL.", "portfolio", "webapp", 0.9),
        ("Led migration from monolith to microservices.", "resume", "webapp", 0.9),
    ]
    for summary, type_, project, confidence in memories:
        mid = tmp_db.insert(
            summary=summary,
            project=project,
            type_=type_,
            source="session",
            confidence=confidence,
            approved=True,
        )
        tmp_vector.add(mid, summary, {"project": project, "type": type_, "source": "session"})

    return tmp_db, tmp_vector


# ── Diff parsing ─────────────────────────────────────────────────────────────

SAMPLE_DIFF = """\
diff --git a/cortec/server.py b/cortec/server.py
index abc1234..def5678 100644
--- a/cortec/server.py
+++ b/cortec/server.py
@@ -10,6 +10,7 @@
 from .config import DEFAULT_PROJECT
+from .agents import review_pr

diff --git a/cortec/agents.py b/cortec/agents.py
new file mode 100644
--- /dev/null
+++ b/cortec/agents.py
@@ -0,0 +1,50 @@
+# agent workflows
"""


def test_extract_diff_files():
    files = extract_diff_files(SAMPLE_DIFF)
    assert "cortec/server.py" in files
    assert "cortec/agents.py" in files


def test_extract_diff_files_empty():
    assert extract_diff_files("") == []


def test_extract_diff_files_no_diff_header():
    assert extract_diff_files("just some random text") == []


# ── Keyword extraction ───────────────────────────────────────────────────────

def test_extract_keywords_basic():
    keywords = _extract_keywords("Fix the vector search bug in Chroma storage")
    lower = [k.lower() for k in keywords]
    assert "vector" in lower
    assert "search" in lower
    assert "chroma" in lower
    assert "storage" in lower


def test_extract_keywords_stops_at_max():
    keywords = _extract_keywords("one two three four five six seven eight nine ten", max_keywords=3)
    assert len(keywords) == 3


def test_extract_keywords_empty():
    assert _extract_keywords("") == []


def test_extract_keywords_filters_stopwords():
    keywords = _extract_keywords("the is a an of in for on with to")
    assert keywords == []


# ── PR Review Agent ──────────────────────────────────────────────────────────

def test_review_pr_returns_result(seeded_stores):
    db, vector = seeded_stores
    result = review_pr(diff=SAMPLE_DIFF, db=db, vector=vector, project="cortec")
    assert isinstance(result, ReviewResult)
    assert result.memories_consulted > 0


def test_review_pr_finds_related_memories(seeded_stores):
    db, vector = seeded_stores
    diff = """\
diff --git a/cortec/storage/vector.py b/cortec/storage/vector.py
--- a/cortec/storage/vector.py
+++ b/cortec/storage/vector.py
@@ -40,7 +40,7 @@
-        results = self._col.query(query_texts=[query])
+        results = self._col.query(query_texts=[query], n_results=top_k)
"""
    result = review_pr(diff=diff, db=db, vector=vector, project="cortec")
    assert len(result.findings) > 0
    types_found = {f.memory_type for f in result.findings}
    assert len(types_found) >= 1


def test_review_pr_includes_files_analyzed(seeded_stores):
    db, vector = seeded_stores
    result = review_pr(diff=SAMPLE_DIFF, db=db, vector=vector)
    assert "cortec/server.py" in result.files_analyzed


def test_review_pr_empty_vector_store(tmp_db, tmp_vector):
    result = review_pr(diff=SAMPLE_DIFF, db=tmp_db, vector=tmp_vector)
    assert result.findings == []
    assert result.memories_consulted == 0


def test_review_pr_findings_have_suggestions(seeded_stores):
    db, vector = seeded_stores
    result = review_pr(diff=SAMPLE_DIFF, db=db, vector=vector, project="cortec")
    for f in result.findings:
        assert f.suggestion
        assert f.memory_id
        assert isinstance(f.relevance_score, float)


def test_review_pr_sorted_by_relevance(seeded_stores):
    db, vector = seeded_stores
    result = review_pr(diff=SAMPLE_DIFF, db=db, vector=vector, project="cortec")
    if len(result.findings) >= 2:
        scores = [f.relevance_score for f in result.findings]
        assert scores == sorted(scores, reverse=True)


# ── Debug Assistant ──────────────────────────────────────────────────────────

def test_debug_assist_returns_result(seeded_stores):
    db, vector = seeded_stores
    result = debug_assist(
        error="IndexError in Chroma search on empty collection",
        db=db, vector=vector, project="cortec",
    )
    assert isinstance(result, DebugResult)
    assert result.memories_consulted > 0


def test_debug_assist_finds_bugs_and_fixes(seeded_stores):
    db, vector = seeded_stores
    result = debug_assist(
        error="Chroma search fails with empty collection",
        db=db, vector=vector, project="cortec",
    )
    types_found = {s.memory_type for s in result.suggestions}
    assert "bug" in types_found or "fix" in types_found


def test_debug_assist_separates_patterns(seeded_stores):
    db, vector = seeded_stores
    result = debug_assist(
        error="SQLite connection management context manager",
        db=db, vector=vector, project="cortec",
    )
    if result.patterns:
        for p in result.patterns:
            assert p.memory_type == "pattern"


def test_debug_assist_empty_vector_store(tmp_db, tmp_vector):
    result = debug_assist(error="some error", db=tmp_db, vector=tmp_vector)
    assert result.suggestions == []
    assert result.patterns == []
    assert result.memories_consulted == 0


def test_debug_assist_sorted_by_relevance(seeded_stores):
    db, vector = seeded_stores
    result = debug_assist(
        error="vector storage bug",
        db=db, vector=vector, project="cortec",
    )
    if len(result.suggestions) >= 2:
        scores = [s.relevance_score for s in result.suggestions]
        assert scores == sorted(scores, reverse=True)


def test_debug_assist_no_project_filter(seeded_stores):
    db, vector = seeded_stores
    result = debug_assist(
        error="vector search empty collection",
        db=db, vector=vector,
    )
    assert result.memories_consulted > 0


# ── Portfolio Builder ────────────────────────────────────────────────────────

def test_build_portfolio_returns_result(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db)
    assert isinstance(result, PortfolioResult)
    assert result.total == 4
    assert "cortec" in result.projects
    assert "webapp" in result.projects


def test_build_portfolio_filters_by_project(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db, project="cortec")
    assert result.total == 2
    assert all(e.project == "cortec" for e in result.entries)


def test_build_portfolio_only_portfolio_and_resume(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db)
    for e in result.entries:
        assert e.memory_type in ("portfolio", "resume")


def test_build_portfolio_empty(tmp_db):
    result = build_portfolio(db=tmp_db)
    assert result.total == 0
    assert result.entries == []
    assert result.projects == []


def test_build_portfolio_sorted_by_project_and_date(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db)
    for i in range(len(result.entries) - 1):
        a, b = result.entries[i], result.entries[i + 1]
        assert (a.project, a.created_at) <= (b.project, b.created_at)


# ── Markdown rendering ──────────────────────────────────────────────────────

def test_render_portfolio_markdown(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db)
    md = render_portfolio_markdown(result)
    assert "# Portfolio" in md
    assert "## cortec" in md
    assert "## webapp" in md
    assert "local-first memory server" in md
    assert "4 entries across 2 project(s)" in md


def test_render_portfolio_markdown_empty():
    result = PortfolioResult()
    md = render_portfolio_markdown(result)
    assert "No portfolio or resume entries found" in md


def test_render_portfolio_markdown_labels_types(seeded_stores):
    db, _ = seeded_stores
    result = build_portfolio(db=db)
    md = render_portfolio_markdown(result)
    assert "**Achievement**:" in md
    assert "**Project**:" in md

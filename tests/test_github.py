"""
Tests for GitHub integration — fetcher, confidence scoring, and DB linking.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cortec.github import fetch_commits, fetch_prs, fetch_issues, _gh_available
from cortec.config import Confidence
from cortec.storage.db import MetadataStore


# ── Confidence scoring ────────────────────────────────────────────────────────

def test_github_commit_confidence():
    assert Confidence.from_source("github_commit") == 0.8


def test_github_pr_confidence():
    assert Confidence.from_source("github_pr") == 0.8


def test_github_issue_confidence():
    assert Confidence.from_source("github_issue") == 0.8


def test_session_confidence():
    assert Confidence.from_source("session") == 0.7


def test_stackoverflow_confidence():
    assert Confidence.from_source("stackoverflow") == 0.6


def test_unknown_source_defaults_to_inferred():
    assert Confidence.from_source("magic") == 0.5


# ── Fetcher (mocked gh CLI calls) ────────────────────────────────────────────

MOCK_COMMITS = [
    {
        "sha": "abc1234567890",
        "commit": {
            "message": "fix: resolve memory leak in vector store",
            "author": {"name": "Raj Kumar Satya", "date": "2026-05-27T10:00:00Z"},
        },
    },
    {
        "sha": "def9876543210",
        "commit": {
            "message": "feat: add conflict detection engine",
            "author": {"name": "Raj Kumar Satya", "date": "2026-05-26T15:00:00Z"},
        },
    },
]

MOCK_PRS = [
    {
        "number": 1,
        "title": "Add Phase 2 features",
        "body": "Memory types, conflict detection, project_context tool.",
        "state": "closed",
        "html_url": "https://github.com/rajkumar-prog/cortec-mcp/pull/1",
        "merged_at": "2026-05-27T12:00:00Z",
    }
]

MOCK_ISSUES = [
    {
        "number": 5,
        "title": "Chroma fails on empty collection search",
        "body": "Calling search() on an empty Chroma collection raises an exception.",
        "state": "closed",
        "html_url": "https://github.com/rajkumar-prog/cortec-mcp/issues/5",
    }
]


def _mock_run(data):
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps(data)
    return m


@patch("cortec.github.subprocess.run")
def test_fetch_commits(mock_run):
    mock_run.return_value = _mock_run(MOCK_COMMITS)
    commits = fetch_commits("owner/repo", limit=2)
    assert len(commits) == 2
    assert commits[0].sha == "abc123456789"  # truncated to 12 chars
    assert "resolve memory leak" in commits[0].message
    assert commits[0].author == "Raj Kumar Satya"


@patch("cortec.github.subprocess.run")
def test_fetch_prs(mock_run):
    mock_run.return_value = _mock_run(MOCK_PRS)
    prs = fetch_prs("owner/repo", limit=1)
    assert len(prs) == 1
    assert prs[0].number == 1
    assert prs[0].title == "Add Phase 2 features"
    assert prs[0].merged_at == "2026-05-27T12:00:00Z"


@patch("cortec.github.subprocess.run")
def test_fetch_issues(mock_run):
    mock_run.return_value = _mock_run(MOCK_ISSUES)
    issues = fetch_issues("owner/repo", limit=1)
    assert len(issues) == 1
    assert issues[0].number == 5
    assert issues[0].state == "closed"


@patch("cortec.github._gh_available", return_value=True)
@patch("cortec.github.subprocess.run")
def test_fetch_commits_gh_error(mock_run, _mock_avail):
    m = MagicMock()
    m.returncode = 1
    m.stderr = "gh: not logged in"
    m.stdout = ""
    mock_run.return_value = m
    with pytest.raises(RuntimeError, match="not logged in"):
        fetch_commits("owner/repo")


# ── DB commit linking ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    return MetadataStore(tmp_path / "test.db")


def test_insert_with_commit_sha(tmp_db):
    mid = tmp_db.insert(
        summary="Fixed null pointer in recall()",
        project="cortec",
        type_="fix",
        source="github_commit",
        approved=True,
        commit_sha="abc123",
    )
    meta = tmp_db.get(mid)
    assert meta["commit_sha"] == "abc123"


def test_link_to_commit(tmp_db):
    mid = tmp_db.insert(summary="some fix", approved=True)
    assert tmp_db.get(mid)["commit_sha"] is None
    updated = tmp_db.link_to_commit(mid, "deadbeef")
    assert updated is True
    assert tmp_db.get(mid)["commit_sha"] == "deadbeef"


def test_get_by_commit(tmp_db):
    sha = "cafebabe"
    m1 = tmp_db.insert(summary="fix A", approved=True, commit_sha=sha)
    m2 = tmp_db.insert(summary="fix B", approved=True, commit_sha=sha)
    m3 = tmp_db.insert(summary="unrelated", approved=True)

    related = tmp_db.get_by_commit(sha)
    ids = {m["id"] for m in related}
    assert m1 in ids
    assert m2 in ids
    assert m3 not in ids


def test_link_nonexistent_memory(tmp_db):
    updated = tmp_db.link_to_commit("nonexistent", "sha123")
    assert updated is False

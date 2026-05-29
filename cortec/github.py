"""
GitHub integration — fetches commits, PRs, and issues via the gh CLI.
Requires `gh` to be installed and authenticated.
"""

import json
import subprocess
from dataclasses import dataclass


@dataclass
class GithubCommit:
    sha: str
    message: str
    author: str
    date: str


@dataclass
class GithubPR:
    number: int
    title: str
    body: str
    state: str
    url: str
    merged_at: str | None


@dataclass
class GithubIssue:
    number: int
    title: str
    body: str
    state: str
    url: str


def _gh_available() -> bool:
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _api(path: str, params: dict | None = None) -> list | dict:
    cmd = ["gh", "api", path]
    if params:
        for key, val in params.items():
            cmd += ["-F", f"{key}={val}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh api {path} failed")
    return json.loads(result.stdout)


def fetch_commits(repo: str, limit: int = 20) -> list[GithubCommit]:
    """Fetch recent commits from a GitHub repo."""
    if not _gh_available():
        raise RuntimeError("gh CLI is not installed or not in PATH.")
    data = _api(f"repos/{repo}/commits", {"per_page": limit})
    commits = []
    for item in data[:limit]:
        commit = item.get("commit", {})
        commits.append(GithubCommit(
            sha=item.get("sha", "")[:12],
            message=commit.get("message", "").split("\n")[0],
            author=commit.get("author", {}).get("name", "unknown"),
            date=commit.get("author", {}).get("date", ""),
        ))
    return commits


def fetch_prs(repo: str, state: str = "closed", limit: int = 20) -> list[GithubPR]:
    """Fetch pull requests from a GitHub repo."""
    if not _gh_available():
        raise RuntimeError("gh CLI is not installed or not in PATH.")
    data = _api(f"repos/{repo}/pulls", {"state": state, "per_page": limit})
    prs = []
    for item in data[:limit]:
        prs.append(GithubPR(
            number=item.get("number", 0),
            title=item.get("title", ""),
            body=(item.get("body") or "")[:500],
            state=item.get("state", ""),
            url=item.get("html_url", ""),
            merged_at=item.get("merged_at"),
        ))
    return prs


def fetch_issues(repo: str, state: str = "closed", limit: int = 20) -> list[GithubIssue]:
    """Fetch issues from a GitHub repo (excludes pull requests)."""
    if not _gh_available():
        raise RuntimeError("gh CLI is not installed or not in PATH.")
    data = _api(f"repos/{repo}/issues", {"state": state, "per_page": limit})
    issues = []
    for item in data[:limit]:
        if "pull_request" in item:
            continue  # gh issues endpoint includes PRs — skip them
        issues.append(GithubIssue(
            number=item.get("number", 0),
            title=item.get("title", ""),
            body=(item.get("body") or "")[:500],
            state=item.get("state", ""),
            url=item.get("html_url", ""),
        ))
    return issues

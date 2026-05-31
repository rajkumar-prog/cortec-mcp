"""
Stack Overflow integration — fetches questions and answers via the Stack Exchange API.
No API key required for read-only access (300 requests/day unauthenticated).
"""

import re
import html
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


_BASE = "https://api.stackexchange.com/2.3"
_FILTER = "withbody"
_SITE = "stackoverflow"


@dataclass
class SOAnswer:
    answer_id: int
    question_id: int
    question_title: str
    answer_body: str
    score: int
    is_accepted: bool
    url: str


@dataclass
class SOQuestion:
    question_id: int
    title: str
    body: str
    score: int
    answer_count: int
    answers: list[SOAnswer]
    url: str


def parse_so_url(url: str) -> tuple[str, int]:
    """
    Parse a Stack Overflow URL and return ('question'|'answer', id).

    Supported formats:
      https://stackoverflow.com/questions/1234/title         -> question 1234
      https://stackoverflow.com/questions/1234/title#5678    -> answer 5678
      https://stackoverflow.com/a/5678                       -> answer 5678
    """
    # Answer short URL: /a/5678
    m = re.search(r"stackoverflow\.com/a/(\d+)", url)
    if m:
        return "answer", int(m.group(1))

    # Question URL with answer anchor: /questions/1234/title#5678
    m = re.search(r"stackoverflow\.com/questions/\d+[^#]*#(\d+)", url)
    if m:
        return "answer", int(m.group(1))

    # Plain question URL: /questions/1234
    m = re.search(r"stackoverflow\.com/questions/(\d+)", url)
    if m:
        return "question", int(m.group(1))

    raise ValueError(f"Cannot parse Stack Overflow URL: {url}")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get(path: str, params: dict) -> dict:
    """
    Call the Stack Exchange API and return the parsed JSON response.

    Respects the Stack Exchange backoff directive — if the response contains
    a ``backoff`` field, the function sleeps for that many seconds before
    returning so subsequent calls are not rate-limited. Raises a clear error
    if the daily quota has been exhausted.
    """
    params.setdefault("site", _SITE)
    params.setdefault("filter", _FILTER)
    resp = httpx.get(f"{_BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if backoff := data.get("backoff"):
        time.sleep(int(backoff))

    if data.get("quota_remaining", 1) == 0:
        raise RuntimeError(
            "Stack Exchange API daily quota exhausted. Try again tomorrow."
        )

    return data


def fetch_answer(answer_id: int) -> SOAnswer:
    """Fetch a single Stack Overflow answer by ID."""
    data = _get(f"/answers/{answer_id}", {})
    items = data.get("items", [])
    if not items:
        raise ValueError(f"Answer {answer_id} not found.")

    item = items[0]
    qid = item.get("question_id", 0)

    # Fetch the question title
    q_data = _get(f"/questions/{qid}", {"filter": "default"})
    q_items = q_data.get("items", [])
    title = q_items[0].get("title", "") if q_items else ""

    return SOAnswer(
        answer_id=answer_id,
        question_id=qid,
        question_title=_strip_html(title),
        answer_body=_strip_html(item.get("body", "")),
        score=item.get("score", 0),
        is_accepted=item.get("is_accepted", False),
        url=f"https://stackoverflow.com/a/{answer_id}",
    )


def fetch_question(question_id: int) -> SOQuestion:
    """Fetch a question and its answers by question ID."""
    data = _get(f"/questions/{question_id}", {})
    items = data.get("items", [])
    if not items:
        raise ValueError(f"Question {question_id} not found.")

    item = items[0]

    ans_data = _get(f"/questions/{question_id}/answers", {"sort": "votes", "order": "desc"})
    answers = [
        SOAnswer(
            answer_id=a["answer_id"],
            question_id=question_id,
            question_title=_strip_html(item.get("title", "")),
            answer_body=_strip_html(a.get("body", ""))[:1000],
            score=a.get("score", 0),
            is_accepted=a.get("is_accepted", False),
            url=f"https://stackoverflow.com/a/{a['answer_id']}",
        )
        for a in ans_data.get("items", [])[:5]
    ]

    return SOQuestion(
        question_id=question_id,
        title=_strip_html(item.get("title", "")),
        body=_strip_html(item.get("body", ""))[:500],
        score=item.get("score", 0),
        answer_count=item.get("answer_count", 0),
        answers=answers,
        url=f"https://stackoverflow.com/questions/{question_id}",
    )


def canonical_url(url: str) -> str:
    """
    Return the canonical form of a Stack Overflow URL.

    Normalises different URL formats for the same content to a single
    stable form so that duplicate detection works regardless of how the
    URL was copied:
      - answers  → https://stackoverflow.com/a/{id}
      - questions → https://stackoverflow.com/questions/{id}

    Raises ValueError if the URL hostname is not stackoverflow.com.
    """
    host = (urlparse(url).hostname or "").lower()
    if host not in {"stackoverflow.com", "www.stackoverflow.com"}:
        raise ValueError(f"Cannot parse Stack Overflow URL: {url}")
    kind, id_ = parse_so_url(url)
    if kind == "answer":
        return f"https://stackoverflow.com/a/{id_}"
    return f"https://stackoverflow.com/questions/{id_}"


def fetch_from_url(url: str) -> SOAnswer | SOQuestion:
    """Fetch content from any Stack Overflow URL."""
    kind, id_ = parse_so_url(url)
    if kind == "answer":
        return fetch_answer(id_)
    return fetch_question(id_)


def build_pattern_summary(content: SOAnswer | SOQuestion) -> str:
    """Build a concise pattern summary suitable for storing as a memory."""
    if isinstance(content, SOAnswer):
        lines = [
            f"Q: {content.question_title}",
            f"A (score={content.score}, accepted={content.is_accepted}):",
            content.answer_body[:600],
        ]
        return "\n".join(lines)

    # Question: use the highest-scored answer
    best = next((a for a in content.answers if a.is_accepted), None)
    if not best and content.answers:
        best = content.answers[0]

    lines = [f"Q: {content.title}"]
    if best:
        lines.append(f"A (score={best.score}, accepted={best.is_accepted}):")
        lines.append(best.answer_body[:600])
    else:
        lines.append(content.body[:600])

    return "\n".join(lines)

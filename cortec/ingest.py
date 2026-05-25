"""
Session ingestion — parses raw session text into clean, storable chunks.
Archives raw sessions to JSONL before indexing.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Archive ───────────────────────────────────────────────────────────────────

def archive_session(
    raw_text: str,
    project: str,
    archive_dir: Path,
) -> Path:
    """Write raw session text to JSONL archive. Returns path to archive file."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_file = archive_dir / f"{project}_{date_str}.jsonl"
    entry = {
        "project": project,
        "captured_at": _now(),
        "text": raw_text,
    }
    with open(archive_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return archive_file


# ── Summarize ─────────────────────────────────────────────────────────────────

def extractive_summarize(text: str, max_sentences: int = 6) -> str:
    """
    Extractive summarizer — selects high-signal sentences.
    No external dependencies. Used as default fallback.
    """
    # Signal keywords: decisions, bugs, fixes, architecture
    keywords = [
        "decided", "decision", "use ", "chose", "switched",
        "bug", "error", "fix", "fixed", "issue", "problem",
        "architecture", "structure", "pattern",
        "install", "import", "dependency",
        "important", "remember", "note",
        "do not", "don't", "avoid", "never",
        "always", "must", "should",
    ]
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    scored: list[tuple[int, str]] = []
    for i, sentence in enumerate(sentences):
        s = sentence.lower()
        score = sum(1 for kw in keywords if kw in s)
        # Slightly prefer earlier sentences
        score += max(0, 5 - i // 10)
        if len(sentence.split()) >= 5:  # skip very short fragments
            scored.append((score, sentence))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [s for _, s in scored[:max_sentences]]
    return " ".join(selected) if selected else text[:500]


def summarize(
    text: str,
    llm_endpoint: str | None = None,
    llm_model: str | None = None,
) -> str:
    """
    Summarize session text.
    If llm_endpoint is set, calls an OpenAI-compatible API.
    Otherwise falls back to extractive summarization.
    """
    if llm_endpoint:
        return _llm_summarize(text, llm_endpoint, llm_model or "llama3")
    return extractive_summarize(text)


def _llm_summarize(text: str, endpoint: str, model: str) -> str:
    """Call an OpenAI-compatible local LLM endpoint for summarization."""
    try:
        import httpx
        prompt = (
            "Summarize the following developer session into 3-5 concise bullet points. "
            "Focus on: decisions made, bugs found, fixes applied, architecture choices. "
            "Be specific. Skip filler.\n\n"
            f"{text[:4000]}"
        )
        response = httpx.post(
            f"{endpoint}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.3,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        # Always fall back — never fail silently
        return extractive_summarize(text)


# ── Chunk ─────────────────────────────────────────────────────────────────────

def chunk_by_topic(text: str, max_chunk: int = 800) -> list[str]:
    """
    Split session text into topic-aware chunks.
    Prefers splitting at natural boundaries (headings, blank lines, sentences).
    """
    # Split on double newlines first (natural topic breaks)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < max_chunk:
            current += (" " if current else "") + para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks or [text[:max_chunk]]

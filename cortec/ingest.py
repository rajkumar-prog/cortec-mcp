"""
Session ingestion — archives raw sessions and summarizes them.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def archive_session(raw_text: str, project: str, archive_dir: Path) -> Path:
    """Write raw session text to JSONL archive. Returns the archive file path."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_file = archive_dir / f"{project}_{date_str}.jsonl"
    entry = {
        "project": project,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "text": raw_text,
    }
    with open(archive_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return archive_file


def extractive_summarize(text: str, max_sentences: int = 6) -> str:
    """Pick the most signal-rich sentences from session text."""
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
    scored = []
    for i, sentence in enumerate(sentences):
        s = sentence.lower()
        score = sum(1 for kw in keywords if kw in s)
        score += max(0, 5 - i // 10)  # slight preference for earlier sentences
        if len(sentence.split()) >= 5:
            scored.append((score, sentence))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [s for _, s in scored[:max_sentences]]
    return " ".join(selected) if selected else text[:500]


def summarize(
    text: str,
    llm_endpoint: str | None = None,
    llm_model: str | None = None,
) -> str:
    """Summarize session text. Uses a local LLM if endpoint is provided, else extractive."""
    if llm_endpoint:
        return _llm_summarize(text, llm_endpoint, llm_model or "llama3")
    return extractive_summarize(text)


def _llm_summarize(text: str, endpoint: str, model: str) -> str:
    """Call an OpenAI-compatible local LLM to summarize the session."""
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
        return extractive_summarize(text)

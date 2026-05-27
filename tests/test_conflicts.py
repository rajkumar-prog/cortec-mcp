"""
Tests for conflict detection engine.
"""

import pytest
from cortec.conflicts import detect, ConflictResult


def _mem(id: str, summary: str, type_: str = "decision", project: str = "test") -> dict:
    return {"id": id, "summary": summary, "type": type_, "project": project}


class TestConflictDetection:
    def test_no_conflict_clean_memories(self):
        existing = [_mem("a1", "We use Chroma for vector storage.")]
        result = detect(
            new_text="We store sessions in JSONL archives.",
            existing_memories=existing,
            project="test",
            type_="decision",
        )
        assert result.found is False

    def test_detects_vector_db_conflict(self):
        existing = [_mem("a1", "We use Chroma for vector storage.")]
        result = detect(
            new_text="We use Qdrant for vector storage.",
            existing_memories=existing,
            project="test",
            type_="decision",
        )
        assert result.found is True
        assert result.existing_id == "a1"
        assert "vector database" in result.description.lower() or "conflict" in result.description.lower()

    def test_detects_web_framework_conflict(self):
        existing = [_mem("b1", "We use Flask as the web framework.")]
        result = detect(
            new_text="We use Django as the web framework.",
            existing_memories=existing,
            project="test",
            type_="decision",
        )
        assert result.found is True

    def test_detects_package_manager_conflict(self):
        existing = [_mem("c1", "We use npm for package management.", type_="preference")]
        result = detect(
            new_text="We use yarn for package management.",
            existing_memories=existing,
            project="test",
            type_="preference",
        )
        assert result.found is True

    def test_no_conflict_different_projects(self):
        existing = [_mem("d1", "We use Chroma.", project="project-a")]
        result = detect(
            new_text="We use Qdrant.",
            existing_memories=existing,
            project="project-b",   # different project
            type_="decision",
        )
        assert result.found is False

    def test_no_conflict_different_types(self):
        existing = [_mem("e1", "We use Chroma.", type_="decision")]
        result = detect(
            new_text="We use Qdrant.",
            existing_memories=existing,
            project="test",
            type_="bug",           # different type — no comparison
        )
        assert result.found is False

    def test_conflict_result_has_description(self):
        existing = [_mem("f1", "We use Flask.")]
        result = detect(
            new_text="We use Django.",
            existing_memories=existing,
            project="test",
            type_="decision",
        )
        assert result.found is True
        assert result.description is not None
        assert len(result.description) > 0

    def test_empty_existing_memories(self):
        result = detect(
            new_text="We use Chroma.",
            existing_memories=[],
            project="test",
            type_="decision",
        )
        assert result.found is False

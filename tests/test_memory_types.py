"""
Tests for memory type validation and type-filtered recall.
"""

import pytest
from cortec.config import validate_type, VALID_TYPES, MEMORY_TYPES


class TestMemoryTypes:
    def test_all_valid_types_accepted(self):
        for t in VALID_TYPES:
            assert validate_type(t) == t

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid memory type"):
            validate_type("unknown_type")

    def test_error_message_lists_valid_types(self):
        with pytest.raises(ValueError) as exc:
            validate_type("blah")
        assert "decision" in str(exc.value)
        assert "bug" in str(exc.value)

    def test_memory_types_have_descriptions(self):
        for type_name, description in MEMORY_TYPES.items():
            assert isinstance(description, str)
            assert len(description) > 0

    def test_expected_types_present(self):
        expected = {
            "decision", "bug", "fix", "architecture",
            "preference", "command", "dependency",
            "pattern", "portfolio", "resume", "general",
        }
        assert expected == VALID_TYPES

    def test_validate_type_returns_string(self):
        result = validate_type("bug")
        assert isinstance(result, str)
        assert result == "bug"

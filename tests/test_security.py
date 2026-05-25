"""
Tests for secret scanning and redaction.
"""

import pytest
from cortec.security.scanner import scan
from cortec.security.redactor import redact


class TestScanner:
    def test_clean_text_passes(self):
        result = scan("We decided to use Chroma for the MVP.")
        assert result.clean is True
        assert result.findings == []

    def test_openai_key_detected(self):
        result = scan("My key is sk-abcdefghijklmnopqrstuvwxyzABCDEFGH")
        assert result.clean is False
        assert any("OpenAI" in f or "api" in f.lower() for f in result.findings)

    def test_github_token_detected(self):
        result = scan("token=ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJK")
        assert result.clean is False

    def test_private_key_detected(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nABCDEF\n-----END RSA PRIVATE KEY-----"
        result = scan(text)
        assert result.clean is False

    def test_env_password_detected(self):
        result = scan("PASSWORD=mysecretpassword123")
        assert result.clean is False


class TestRedactor:
    def test_openai_key_redacted(self):
        text = "key: sk-abcdefghijklmnopqrstuvwxyzABCDEFGH"
        out  = redact(text)
        assert "sk-" not in out
        assert "REDACTED" in out

    def test_clean_text_unchanged(self):
        text = "We use Chroma for vector storage."
        assert redact(text) == text

    def test_github_token_redacted(self):
        text = "ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"
        out  = redact(text)
        assert "ghp_" not in out
        assert "REDACTED" in out

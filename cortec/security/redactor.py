"""
Redactor — replaces detected secrets with safe placeholders before storing.
"""

import re

_REDACTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9]{32,}"),                     "[REDACTED:openai-key]"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{32,}"),              "[REDACTED:api-key]"),
    (re.compile(r"gh[ps]_[A-Za-z0-9]{36,}"),                 "[REDACTED:github-token]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),            "[REDACTED:github-pat]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"),                         "[REDACTED:aws-key]"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"),
                                                               "[REDACTED:private-key]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_]{20,}"),        "Bearer [REDACTED:token]"),
    (re.compile(r"hf_[A-Za-z0-9]{32,}"),                     "[REDACTED:hf-token]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]+"),               "[REDACTED:slack-token]"),
    (re.compile(r"sk_live_[A-Za-z0-9]{24,}"),                "[REDACTED:stripe-key]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"),                  "[REDACTED:google-key]"),
    (re.compile(r"(?i)(API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE_KEY)(\s*=\s*)(.{6,})", re.MULTILINE),
                                                               r"\1\2[REDACTED]"),
    (re.compile(r"([a-z]+://[^:@\s]+:)[^:@\s]{6,}(@)"),      r"\1[REDACTED]\2"),
]


def redact(text: str) -> str:
    """Replace known secret patterns with safe placeholders."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text

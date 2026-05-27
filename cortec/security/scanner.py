"""
Secret scanner — detects sensitive data before anything is stored.
If secrets are found, storage is blocked.
"""

import re
from dataclasses import dataclass


@dataclass
class ScanResult:
    clean: bool
    findings: list[str]

    def __bool__(self) -> bool:
        return self.clean


# Ordered from most specific to least specific
_PATTERNS = [
    ("OpenAI API key",       re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("Anthropic API key",    re.compile(r"sk-ant-[A-Za-z0-9\-_]{32,}")),
    ("GitHub token",         re.compile(r"gh[ps]_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained",  re.compile(r"github_pat_[A-Za-z0-9_]{82,}")),
    ("AWS access key",       re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS secret key",       re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]")),
    ("Private key block",    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Generic Bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_]{20,}")),
    ("Basic auth header",    re.compile(r"(?i)authorization:\s*basic\s+[A-Za-z0-9+/=]{10,}")),
    ("Password in URL",      re.compile(r"[a-z]+://[^:@\s]+:[^:@\s]{6,}@")),
    ("Generic .env secret",  re.compile(r"(?i)^(API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE_KEY)\s*=\s*.{6,}", re.MULTILINE)),
    ("HuggingFace token",    re.compile(r"hf_[A-Za-z0-9]{32,}")),
    ("Slack token",          re.compile(r"xox[baprs]-[A-Za-z0-9\-]+")),
    ("Stripe secret key",    re.compile(r"sk_live_[A-Za-z0-9]{24,}")),
    ("Google API key",       re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
]


def scan(text: str) -> ScanResult:
    """Scan text for secrets. Returns clean=True if safe, clean=False with findings if not."""
    findings = [label for label, pattern in _PATTERNS if pattern.search(text)]
    return ScanResult(clean=len(findings) == 0, findings=findings)

"""
Normalize error messages and stacks into stable fingerprints.

Fingerprinting strips volatile tokens (line numbers, memory addresses,
file paths, timestamps) so the same logical error maps to the same hash
across runs, even when line numbers shift or paths change.
"""

import hashlib
import re

# Volatile token patterns — order matters (most specific first)
_LINE_COL_RE = re.compile(r"\b\d+:\d+\b")               # 42:7
_LINE_REF_RE = re.compile(r"\bat line \d+\b", re.I)      # at line 42
_HEX_ADDR_RE = re.compile(r"\b0x[0-9a-fA-F]{4,}\b")     # 0xdeadbeef
_HEX_HASH_RE = re.compile(r"\b[0-9a-f]{12,}\b")          # long hex strings (git shas etc)
_ABS_PATH_RE = re.compile(r"(/[\w./\-@]+|[A-Z]:\\[\w\\./\-]+)")  # /home/runner/... or C:\foo
_DIGITS_RE   = re.compile(r"\b\d{3,}\b")                  # standalone numbers ≥3 digits
_WHITESPACE  = re.compile(r"\s+")


def normalize_error(message: str | None, stack: str | None) -> str:
    """Return a whitespace-collapsed, token-stripped representation."""
    text = f"{message or ''}\n{stack or ''}"
    text = _LINE_COL_RE.sub("<POS>", text)
    text = _LINE_REF_RE.sub("<LINE>", text)
    text = _HEX_ADDR_RE.sub("<HEX>", text)
    text = _HEX_HASH_RE.sub("<HASH>", text)
    text = _ABS_PATH_RE.sub("<PATH>", text)
    text = _DIGITS_RE.sub("<N>", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def fingerprint(message: str | None, stack: str | None) -> str:
    """12-char hex fingerprint stable across runs for the same logical error."""
    normalized = normalize_error(message, stack)
    return hashlib.sha1(normalized.encode()).hexdigest()[:12]

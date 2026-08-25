"""Centralized redaction for logs, errors, and shareable diagnostics."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|espn[_-]?s2|espn[_-]?swid|swid|token|password|secret|api[_-]?key)",
    re.IGNORECASE,
)
_AUTH_VALUE = re.compile(r"\b(Basic|Bearer)\s+[^\s,;]+", re.IGNORECASE)
_COOKIE_VALUE = re.compile(r"\b(espn_s2|swid)\s*=\s*[^;\s]+", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>\"']+")


def _known_secrets(extra: Sequence[str] = ()) -> tuple[str, ...]:
    environment = (os.environ.get("ESPN_S2", ""), os.environ.get("ESPN_SWID", ""))
    return tuple(value for value in (*environment, *extra) if value)


def _redact_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    suffix = ""
    while raw and raw[-1] in ".,);]":
        suffix = raw[-1] + suffix
        raw = raw[:-1]
    try:
        parts = urlsplit(raw)
        if not parts.query:
            return raw + suffix
        query = urlencode(
            [(key, REDACTED) for key, _ in parse_qsl(parts.query, keep_blank_values=True)]
        ).replace("%5BREDACTED%5D", REDACTED)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, "")) + suffix
    except ValueError:
        return REDACTED + suffix


def redact_text(value: str, *, secrets: Sequence[str] = ()) -> str:
    """Remove known credentials, auth headers, cookies, and URL query values."""
    redacted = value
    for secret in sorted(_known_secrets(secrets), key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTED)
    redacted = _AUTH_VALUE.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = _COOKIE_VALUE.sub(lambda match: f"{match.group(1)}={REDACTED}", redacted)
    return _URL.sub(_redact_url, redacted)


def redact(value: Any, *, secrets: Sequence[str] = ()) -> Any:
    """Recursively sanitize nested diagnostic context without mutating it."""
    if isinstance(value, BaseException):
        return redact_text(str(value), secrets=secrets)
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(child, secrets=secrets)
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact(child, secrets=secrets) for child in value)
    if isinstance(value, list):
        return [redact(child, secrets=secrets) for child in value]
    if isinstance(value, str):
        return redact_text(value, secrets=secrets)
    return value

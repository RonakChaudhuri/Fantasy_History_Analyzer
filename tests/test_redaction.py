from __future__ import annotations

from fantasy_history.redaction import REDACTED, redact, redact_text


def test_redact_text_covers_auth_cookies_known_secrets_and_url_queries() -> None:
    secret = "sensitive-cookie-value"
    source = (
        "Authorization: Bearer bearer-value; Cookie: espn_s2=cookie-value; SWID={member-id}; "
        f"known={secret}; url=https://example.test/path?token=query-token&season=2025#fragment"
    )

    result = redact_text(source, secrets=(secret,))

    for private_value in (
        "bearer-value",
        "cookie-value",
        "{member-id}",
        secret,
        "query-token",
        "2025",
        "fragment",
    ):
        assert private_value not in result
    assert result.count(REDACTED) >= 6


def test_redact_sanitizes_nested_context_and_exceptions() -> None:
    context = {
        "request": {
            "headers": {"Authorization": "Bearer hidden", "Accept": "application/json"},
            "url": "https://example.test/data?member=private-id",
        },
        "errors": [RuntimeError("Cookie: espn_s2=hidden-cookie")],
        "safe": ("season", 2025),
    }

    result = redact(context)

    serialized = repr(result)
    assert "hidden" not in serialized
    assert "private-id" not in serialized
    assert result["request"]["headers"]["Authorization"] == REDACTED
    assert result["safe"] == ("season", 2025)

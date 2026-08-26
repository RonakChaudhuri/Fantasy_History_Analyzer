from __future__ import annotations

import httpx
import pytest

from fantasy_history.config import load_settings
from fantasy_history.espn_client import EspnAuthenticationError, EspnClient


def settings():
    return load_settings(env={"ESPN_S2": "synthetic-secret", "ESPN_SWID": "{synthetic-swid}"})


def test_historical_fallback_unwraps_list() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "leagueHistory" not in str(request.url):
            return httpx.Response(401)
        return httpx.Response(200, json=[{"settings": {}, "teams": []}])

    client = EspnClient(settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    payload, route = client.fetch(2019, ("mSettings",))

    assert payload == {"settings": {}, "teams": []}
    assert route == "historical"
    assert len(calls) == 2


def test_authentication_is_not_retried_and_error_is_safe() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    client = EspnClient(
        settings(), client=httpx.Client(transport=httpx.MockTransport(handler)), max_attempts=3
    )
    with pytest.raises(EspnAuthenticationError) as captured:
        client.fetch(2019, ("mSettings",))

    assert calls == 2  # one current-route attempt, one historical-route attempt
    assert "synthetic-secret" not in str(captured.value)
    assert "synthetic-swid" not in str(captured.value)


def test_temporary_errors_use_bounded_retries() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"settings": {}, "teams": []})

    sleeps = []
    client = EspnClient(
        settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
    )
    _, route = client.fetch(2025, ("mSettings",))

    assert route == "current"
    assert calls == 3
    assert sleeps == [0.25, 0.5]

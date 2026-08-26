"""Small, injectable ESPN HTTP adapter with safe failures and historical fallback."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import httpx

from fantasy_history.config import Settings
from fantasy_history.validation import ResponseValidationError, unwrap_league_payload

API_ROOT = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
USER_AGENT = "fantasy-history-analyzer/0.2"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EspnClientError(RuntimeError):
    """Safe ESPN boundary error with no body, cookie, or query-string content."""


class EspnAuthenticationError(EspnClientError):
    """ESPN rejected the configured private-league credentials."""


class SeasonUnavailableError(EspnClientError):
    """A calendar season does not contain the configured league."""


class EspnClient:
    """Fetch validated JSON using bounded retries and injectable HTTP transport."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        max_attempts: int = 3,
        backoff: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.settings = settings
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.sleeper = sleeper
        self._owns_client = client is None
        self.client = client or httpx.Client(
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            cookies={
                "espn_s2": settings.espn_s2.get_secret_value(),
                "SWID": settings.espn_swid.get_secret_value(),
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> EspnClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _request(self, *, season: int, url: str, params: list[tuple[str, Any]]) -> Any:
        last_reason = "temporary network failure"
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.get(url, params=params, timeout=self.timeout)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_reason = type(exc).__name__
            else:
                if response.status_code in (401, 403):
                    raise EspnAuthenticationError(
                        f"ESPN rejected access for season {season}; refresh local credentials."
                    )
                if response.status_code in (400, 404):
                    raise SeasonUnavailableError(f"League season {season} is unavailable.")
                if response.status_code not in RETRYABLE_STATUS:
                    try:
                        response.raise_for_status()
                        return response.json()
                    except ValueError:
                        raise EspnClientError(
                            f"ESPN returned invalid JSON for season {season}."
                        ) from None
                    except httpx.HTTPStatusError:
                        raise EspnClientError(
                            f"ESPN request failed for season {season} "
                            f"(HTTP {response.status_code})."
                        ) from None
                last_reason = f"HTTP {response.status_code}"
            if attempt < self.max_attempts:
                self.sleeper(self.backoff * (2 ** (attempt - 1)))
        raise EspnClientError(
            f"ESPN request for season {season} failed after {self.max_attempts} attempts "
            f"({last_reason})."
        )

    def fetch(
        self,
        season: int,
        views: Iterable[str],
        extra_params: Mapping[str, int | str] | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Fetch a league view, falling back to leagueHistory on current-route auth failure."""
        params: list[tuple[str, Any]] = [("view", view) for view in views]
        params.extend((extra_params or {}).items())
        current_url = f"{API_ROOT}/seasons/{season}/segments/0/leagues/{self.settings.league_id}"
        try:
            raw = self._request(season=season, url=current_url, params=params)
            payload, _ = unwrap_league_payload(raw, season=season)
            return payload, "current"
        except EspnAuthenticationError:
            history_url = f"{API_ROOT}/leagueHistory/{self.settings.league_id}"
            raw = self._request(
                season=season,
                url=history_url,
                params=[("seasonId", season), *params],
            )
            try:
                payload, _ = unwrap_league_payload(raw, season=season)
            except ResponseValidationError as exc:
                raise EspnClientError(str(exc)) from None
            return payload, "historical"

    def discover_latest(self, *, current_year: int) -> int:
        """Find the newest accessible league season without assuming it is complete."""
        for season in range(current_year, self.settings.first_season - 1, -1):
            try:
                payload, _ = self.fetch(season, ("mSettings", "mTeam"))
            except SeasonUnavailableError:
                continue
            if payload.get("settings") and payload.get("teams"):
                return season
        raise SeasonUnavailableError("No accessible league season was found.")

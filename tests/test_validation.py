from __future__ import annotations

import pytest

from fantasy_history.validation import (
    CoverageStatus,
    ResponseValidationError,
    collection_coverage,
    unwrap_league_payload,
    validate_league_identity,
)


def test_coverage_distinguishes_unavailable_empty_partial_and_complete() -> None:
    assert collection_coverage(present=False, count=0).status == CoverageStatus.UNAVAILABLE
    assert collection_coverage(present=True, count=0).status == CoverageStatus.AVAILABLE_EMPTY
    assert collection_coverage(present=True, count=2, partial=True).status == CoverageStatus.PARTIAL
    assert collection_coverage(present=True, count=2).status == CoverageStatus.COMPLETE


def test_historical_envelope_and_identity_are_strict() -> None:
    payload, historical = unwrap_league_payload([{"id": 999, "seasonId": 2019}], season=2019)
    assert historical is True
    validate_league_identity(payload, league_id=999, season=2019)

    with pytest.raises(ResponseValidationError, match="wrong league"):
        validate_league_identity(payload, league_id=1000, season=2019)
    with pytest.raises(ResponseValidationError, match="historical response envelope"):
        unwrap_league_payload([], season=2019)

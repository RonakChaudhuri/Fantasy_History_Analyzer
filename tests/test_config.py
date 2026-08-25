from __future__ import annotations

import pytest
from pydantic import SecretStr

from fantasy_history.config import ConfigurationError, load_settings


def test_settings_load_valid_values_without_exposing_secrets() -> None:
    secret = "credential-value"
    settings = load_settings(
        env={
            "ESPN_LEAGUE_ID": "78212237",
            "ESPN_FIRST_SEASON": "2019",
            "ESPN_S2": secret,
            "ESPN_SWID": "{synthetic-swid}",
        }
    )

    assert settings.league_id == 78212237
    assert isinstance(settings.espn_s2, SecretStr)
    assert secret not in repr(settings)


def test_missing_secrets_raise_safe_actionable_error() -> None:
    with pytest.raises(ConfigurationError) as captured:
        load_settings(env={"ESPN_S2": "do-not-print"})

    message = str(captured.value)
    assert "ESPN_SWID" in message
    assert ".env" in message
    assert "do-not-print" not in message


def test_invalid_public_settings_do_not_include_secret_values() -> None:
    secret = "credential-value"
    with pytest.raises(ConfigurationError) as captured:
        load_settings(
            env={
                "ESPN_LEAGUE_ID": "not-an-integer",
                "ESPN_S2": secret,
                "ESPN_SWID": "{synthetic-swid}",
            }
        )

    assert secret not in str(captured.value)

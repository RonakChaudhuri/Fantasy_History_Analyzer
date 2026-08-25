"""Validated, server-only application configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

DEFAULT_LEAGUE_ID = 78212237
DEFAULT_FIRST_SEASON = 2019
SECRET_NAMES = ("ESPN_S2", "ESPN_SWID")


class ConfigurationError(RuntimeError):
    """A safe, actionable configuration failure."""


class Settings(BaseModel):
    """Validated ESPN settings that keep credentials wrapped as secrets."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    league_id: int = Field(default=DEFAULT_LEAGUE_ID, gt=0)
    first_season: int = Field(default=DEFAULT_FIRST_SEASON, ge=2000, le=2100)
    espn_s2: SecretStr
    espn_swid: SecretStr


def load_settings(
    *,
    env: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> Settings:
    """Load settings without ever embedding secret values in an error."""
    if env is None:
        load_dotenv(env_file or Path(".env"), override=False)
        source: Mapping[str, str] = os.environ
    else:
        source = env

    missing = [name for name in SECRET_NAMES if not source.get(name, "").strip()]
    if missing:
        names = ", ".join(missing)
        pronoun = "them" if len(missing) > 1 else "it"
        raise ConfigurationError(
            f"Missing {names}. Add {pronoun} to the local .env file or deployment secret store; "
            "never paste credentials into chat."
        )

    try:
        return Settings.model_validate(
            {
                "league_id": source.get("ESPN_LEAGUE_ID", str(DEFAULT_LEAGUE_ID)),
                "first_season": source.get("ESPN_FIRST_SEASON", str(DEFAULT_FIRST_SEASON)),
                "espn_s2": source["ESPN_S2"],
                "espn_swid": source["ESPN_SWID"],
            }
        )
    except ValidationError as exc:
        fields = sorted({str(item["loc"][0]) for item in exc.errors() if item["loc"]})
        joined = ", ".join(fields) or "configuration"
        raise ConfigurationError(
            f"Invalid {joined}. Check the local .env file; secret values were not displayed."
        ) from None

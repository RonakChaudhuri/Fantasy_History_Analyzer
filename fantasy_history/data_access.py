"""File-backed reads for UI-ready data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OVERVIEW_PATH = PROJECT_ROOT / "data" / "fixtures" / "demo_overview.json"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
IDENTITIES_ROOT = PROJECT_ROOT / "data" / "derived" / "identities"
ANALYTICS_ROOT = PROJECT_ROOT / "data" / "derived" / "analytics"


def load_demo_overview(path: Path = DEMO_OVERVIEW_PATH) -> dict[str, Any]:
    """Load the committed synthetic overview fixture without network access."""
    with path.open(encoding="utf-8") as fixture:
        payload = json.load(fixture)
    if not isinstance(payload, dict):
        raise ValueError("The demo overview fixture must contain a JSON object.")
    return payload


def champions_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert synthetic champion rows into a chart-ready frame."""
    return pd.DataFrame(payload["champions"])


def load_processed_table(name: str, root: Path = PROCESSED_ROOT) -> pd.DataFrame:
    """Read one normalized table without accessing raw ESPN snapshots."""
    if not name.replace("_", "").isalnum():
        raise ValueError("Invalid processed table name.")
    return pd.read_parquet(root / f"{name}.parquet")


def load_identity_table(name: str, root: Path = IDENTITIES_ROOT) -> pd.DataFrame:
    """Read one promoted Phase 3 identity table."""
    if name not in {"canonical_managers", "manager_team_assignments"}:
        raise ValueError("Unknown identity table name.")
    return pd.read_parquet(root / f"{name}.parquet")


def load_analytics_table(name: str, root: Path = ANALYTICS_ROOT) -> pd.DataFrame:
    """Read one promoted, versioned Phase 4 analytics table."""
    allowed = {
        "matchup_facts",
        "team_standings",
        "season_finishes",
        "weekly_expected_wins",
        "expected_wins",
        "manager_seasons",
        "manager_careers",
        "head_to_head",
        "streaks",
        "record_holders",
    }
    if name not in allowed:
        raise ValueError("Unknown analytics table name.")
    return pd.read_parquet(root / f"{name}.parquet")

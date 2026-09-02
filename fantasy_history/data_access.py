"""File-backed reads for UI-ready data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OVERVIEW_PATH = PROJECT_ROOT / "data" / "fixtures" / "demo_overview.json"
PRIVATE_DATA_ROOT = PROJECT_ROOT / "data"
PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"


def _default_data_root() -> Path:
    """Prefer private local data, falling back to the committed public bundle."""
    if (PRIVATE_DATA_ROOT / "processed" / "seasons.parquet").is_file():
        return PRIVATE_DATA_ROOT
    return PUBLIC_DATA_ROOT


DATA_ROOT = _default_data_root()
PROCESSED_ROOT = DATA_ROOT / "processed"
IDENTITIES_ROOT = DATA_ROOT / "derived" / "identities"
ANALYTICS_ROOT = DATA_ROOT / "derived" / "analytics"
DRAFT_ANALYTICS_ROOT = DATA_ROOT / "derived" / "draft_analytics"

PHASE6_PROCESSED_TABLES = (
    "drafts",
    "draft_picks",
    "players",
    "roster_snapshots",
    "roster_players",
    "player_scores",
)

TRADE_PROCESSED_TABLES = ("trades", "trade_items", "trade_coverage", "players")

REQUIRED_PROCESSED_TABLES = ("seasons", "season_teams", "matchups")
REQUIRED_IDENTITY_TABLES = ("canonical_managers", "manager_team_assignments")
REQUIRED_ANALYTICS_TABLES = (
    "matchup_facts",
    "team_standings",
    "season_finishes",
    "manager_seasons",
    "manager_careers",
    "head_to_head",
    "streaks",
    "record_holders",
)


@dataclass(frozen=True)
class DataReadiness:
    """Share-safe state presented before any private analytics are loaded."""

    status: str
    message: str
    warnings: tuple[str, ...] = ()
    formula_version: str | None = None
    attribution_policy_version: str | None = None
    cache_key: str | None = None

    @property
    def ready(self) -> bool:
        """Whether pages may safely load the promoted bundle."""
        return self.status in {"current", "partial"}


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return payload


def inspect_data_readiness(
    *,
    processed_root: Path = PROCESSED_ROOT,
    identities_root: Path = IDENTITIES_ROOT,
    analytics_root: Path = ANALYTICS_ROOT,
) -> DataReadiness:
    """Validate required files, identity completeness, and analytics currency."""
    required = [processed_root / f"{name}.parquet" for name in REQUIRED_PROCESSED_TABLES]
    required += [identities_root / f"{name}.parquet" for name in REQUIRED_IDENTITY_TABLES]
    required += [analytics_root / f"{name}.parquet" for name in REQUIRED_ANALYTICS_TABLES]
    required += [identities_root / "manifest.json", analytics_root / "manifest.json"]
    if any(not path.is_file() for path in required):
        return DataReadiness(
            "missing",
            "Local history is unavailable. Run the identity validation and analytics rebuild "
            "commands.",
        )
    try:
        identity = _read_json_object(identities_root / "manifest.json")
        analytics = _read_json_object(analytics_root / "manifest.json")
        counts = identity["counts"]
        complete = (
            counts["unresolved_teams"] == 0
            and counts["conflict_count"] == 0
            and counts["resolved_teams"] == counts["total_teams"]
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return DataReadiness("missing", "Local data manifests are missing or invalid.")
    if not complete:
        return DataReadiness(
            "missing", "Manager identities are incomplete. Resolve them before viewing careers."
        )

    # Import locally to keep the basic fixture helper independent from analytics orchestration.
    from fantasy_history.analytics import analytics_bundle_is_current

    if not analytics_bundle_is_current(
        processed_root=processed_root,
        identities_root=identities_root,
        analytics_root=analytics_root,
    ):
        return DataReadiness(
            "stale",
            "Analytics do not match the current sources. Run "
            "`python scripts/rebuild_analytics.py`.",
        )
    warnings = tuple(str(value) for value in analytics.get("coverage_warnings", []))
    status = "partial" if warnings else "current"
    cache_key = hashlib.sha256(
        json.dumps(analytics, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DataReadiness(
        status,
        (
            "Local analytics are ready."
            if not warnings
            else "Local analytics are ready with partial coverage."
        ),
        warnings,
        str(analytics.get("formula_version", "unknown")),
        str(analytics.get("attribution_policy_version", "unknown")),
        cache_key,
    )


def load_analytics_manifest(root: Path = ANALYTICS_ROOT) -> dict[str, Any]:
    """Load the share-safe analytics manifest."""
    return _read_json_object(root / "manifest.json")


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


def load_draft_analytics_manifest(root: Path = DRAFT_ANALYTICS_ROOT) -> dict[str, Any]:
    """Load the share-safe Phase 6 analytics manifest."""
    return _read_json_object(root / "manifest.json")


def load_draft_analytics_table(name: str, root: Path = DRAFT_ANALYTICS_ROOT) -> pd.DataFrame:
    """Read one promoted, versioned Phase 6 analytics table."""
    allowed = {
        "replacement_baselines",
        "draft_pick_values",
        "draft_position_tendencies",
        "repeated_players",
        "draft_report_cards",
    }
    if name not in allowed:
        raise ValueError("Unknown draft analytics table name.")
    return pd.read_parquet(root / f"{name}.parquet")


def phase6_source_cache_key(
    *,
    processed_root: Path = PROCESSED_ROOT,
    identities_root: Path = IDENTITIES_ROOT,
) -> str | None:
    """Hash Phase 6 inputs because Phase 2 has no promoted processed manifest."""
    paths = [processed_root / f"{name}.parquet" for name in PHASE6_PROCESSED_TABLES]
    paths.append(identities_root / "manifest.json")
    if any(not path.is_file() for path in paths):
        return None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def trade_source_cache_key(
    *,
    processed_root: Path = PROCESSED_ROOT,
    identities_root: Path = IDENTITIES_ROOT,
) -> str | None:
    """Hash normalized trade inputs and canonical identity assignments."""
    paths = [processed_root / f"{name}.parquet" for name in TRADE_PROCESSED_TABLES]
    paths.append(identities_root / "manifest.json")
    if any(not path.is_file() for path in paths):
        return None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()

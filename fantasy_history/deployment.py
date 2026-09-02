"""Build a public, read-only data bundle for the deployed Streamlit app."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_history.analytics import PROCESSED_INPUTS as ANALYTICS_INPUTS
from fantasy_history.data_access import PRIVATE_DATA_ROOT, PUBLIC_DATA_ROOT
from fantasy_history.draft_analytics import PROCESSED_INPUTS as DRAFT_INPUTS

DEPLOYMENT_BUNDLE_VERSION = "public.v1"
PROCESSED_TABLES = (
    "draft_picks",
    "drafts",
    "managers",
    "matchups",
    "player_scores",
    "players",
    "playoff_results",
    "roster_players",
    "roster_snapshots",
    "season_teams",
    "seasons",
    "team_scores",
    "trade_coverage",
    "trade_items",
    "trades",
)
DERIVED_TABLES = {
    "identities": ("canonical_managers", "manager_team_assignments"),
    "analytics": (
        "expected_wins",
        "head_to_head",
        "manager_careers",
        "manager_seasons",
        "matchup_facts",
        "record_holders",
        "season_finishes",
        "streaks",
        "team_standings",
        "weekly_expected_wins",
    ),
    "draft_analytics": (
        "draft_pick_values",
        "draft_position_tendencies",
        "draft_report_cards",
        "repeated_players",
        "replacement_baselines",
    ),
}


class DeploymentBundleError(RuntimeError):
    """Raised when a public bundle cannot be produced safely."""


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize_frame(relative_path: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Remove ESPN member identifiers while preserving all rendered values."""
    sanitized = frame.copy()
    for column in ("source_member_id", "primary_owner_id"):
        if column in sanitized:
            sanitized[column] = None
    for column in ("owner_ids_json", "source_member_ids_json", "espn_member_ids_json"):
        if column in sanitized:
            sanitized[column] = "[]"
    if relative_path == "processed/managers.parquet" and "source_row_key" in sanitized:
        sanitized["source_row_key"] = [
            f"manager:{int(season)}:{index + 1}" for index, season in enumerate(sanitized["season"])
        ]
    return sanitized


def _write_frame(source: Path, destination: Path, relative_path: str) -> None:
    try:
        frame = pd.read_parquet(source)
    except (OSError, ValueError) as exc:
        raise DeploymentBundleError(f"Required source table is unavailable: {source.name}") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    _sanitize_frame(relative_path, frame).to_parquet(destination, index=False, compression="zstd")


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentBundleError(f"Required manifest is unavailable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DeploymentBundleError(f"Required manifest is invalid: {path.name}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_staged_bundle(source_root: Path, destination: Path) -> None:
    for name in PROCESSED_TABLES:
        relative = f"processed/{name}.parquet"
        _write_frame(source_root / relative, destination / relative, relative)

    for group, names in DERIVED_TABLES.items():
        for name in names:
            relative = f"derived/{group}/{name}.parquet"
            _write_frame(source_root / relative, destination / relative, relative)

    identity_source = source_root / "derived" / "identities" / "manifest.json"
    identity = _read_manifest(identity_source)
    identity["mapping_checksum"] = "not-distributed"
    identity["source_checksums"] = {
        name: _checksum(destination / "processed" / f"{name}.parquet")
        for name in ("managers", "season_teams")
    }
    identity_path = destination / "derived" / "identities" / "manifest.json"
    _write_json(identity_path, identity)

    analytics = _read_manifest(source_root / "derived" / "analytics" / "manifest.json")
    analytics["processed_source_checksums"] = {
        name: _checksum(destination / "processed" / f"{name}.parquet") for name in ANALYTICS_INPUTS
    }
    analytics["identity_manifest_checksum"] = _checksum(identity_path)
    _write_json(destination / "derived" / "analytics" / "manifest.json", analytics)

    draft = _read_manifest(source_root / "derived" / "draft_analytics" / "manifest.json")
    draft["processed_source_checksums"] = {
        name: _checksum(destination / "processed" / f"{name}.parquet") for name in DRAFT_INPUTS
    }
    draft["identity_manifest_checksum"] = _checksum(identity_path)
    _write_json(destination / "derived" / "draft_analytics" / "manifest.json", draft)

    files = sorted(path for path in destination.rglob("*") if path.is_file())
    _write_json(
        destination / "manifest.json",
        {
            "bundle_version": DEPLOYMENT_BUNDLE_VERSION,
            "files": {path.relative_to(destination).as_posix(): _checksum(path) for path in files},
            "privacy": {
                "contains_credentials": False,
                "contains_raw_espn_responses": False,
                "espn_member_identifiers_removed": True,
                "read_only": True,
            },
        },
    )


def build_deployment_bundle(
    *, source_root: Path = PRIVATE_DATA_ROOT, destination_root: Path = PUBLIC_DATA_ROOT
) -> None:
    """Atomically replace the committed public bundle from valid local data."""
    staging_parent = destination_root.parent
    transaction = staging_parent / f".public-staging-{uuid.uuid4().hex}"
    staged = transaction / "public"
    backup = transaction / "backup"
    transaction.mkdir(parents=True, exist_ok=False)
    try:
        _build_staged_bundle(source_root, staged)
        if destination_root.exists():
            destination_root.replace(backup)
        try:
            staged.replace(destination_root)
        except Exception:
            if destination_root.exists():
                shutil.rmtree(destination_root)
            if backup.exists():
                backup.replace(destination_root)
            raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)

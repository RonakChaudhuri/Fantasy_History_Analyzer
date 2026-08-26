"""Versioned, atomic orchestration for the Phase 4 analytics bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fantasy_history.records import build_record_holders
from fantasy_history.rivalries import (
    attribute_matchup_facts,
    calculate_streaks,
    summarize_head_to_head,
)
from fantasy_history.standings import (
    ATTRIBUTION_POLICY_VERSION,
    FORMULA_VERSION,
    build_manager_seasons,
    build_matchup_facts,
    calculate_expected_wins,
    calculate_season_finishes,
    summarize_manager_careers,
    summarize_team_standings,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
DEFAULT_IDENTITIES_ROOT = PROJECT_ROOT / "data" / "derived" / "identities"
DEFAULT_ANALYTICS_ROOT = PROJECT_ROOT / "data" / "derived" / "analytics"
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "data" / ".staging"
ANALYTICS_SCHEMA_VERSION = "phase4.v1"

PROCESSED_INPUTS = ("seasons", "season_teams", "matchups", "team_scores")


class AnalyticsValidationError(RuntimeError):
    """A safe analytics input, integrity, or promotion failure."""


@dataclass(frozen=True)
class AnalyticsBuildResult:
    """Frames and non-private coverage warnings produced by one build."""

    frames: dict[str, pd.DataFrame]
    warnings: tuple[str, ...]


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_inputs(
    processed_root: Path, identities_root: Path
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    try:
        processed = {
            name: pd.read_parquet(processed_root / f"{name}.parquet") for name in PROCESSED_INPUTS
        }
        assignments = pd.read_parquet(identities_root / "manager_team_assignments.parquet")
        identity_manifest = json.loads((identities_root / "manifest.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AnalyticsValidationError(
            "Processed data or the complete Phase 3 identity bundle is unavailable."
        ) from exc
    counts = identity_manifest.get("counts", {})
    if (
        counts.get("unresolved_teams") != 0
        or counts.get("conflict_count") != 0
        or counts.get("resolved_teams") != counts.get("total_teams")
    ):
        raise AnalyticsValidationError("The Phase 3 identity bundle is not complete.")
    expected_sources = identity_manifest.get("source_checksums", {})
    for name in ("managers", "season_teams"):
        path = processed_root / f"{name}.parquet"
        if expected_sources.get(name) != _checksum(path):
            raise AnalyticsValidationError("The Phase 3 identity bundle is stale.")
    processed["assignments"] = assignments
    return processed, identity_manifest


def build_analytics_frames(inputs: dict[str, pd.DataFrame]) -> AnalyticsBuildResult:
    """Build every analytics output from injected normalized/identity frames."""
    facts = build_matchup_facts(inputs["matchups"])
    standings_by_segment = [
        summarize_team_standings(facts, segment=segment)
        for segment in (
            "regular_season",
            "championship_playoff",
            "consolation",
            "combined",
        )
    ]
    team_standings = pd.concat(standings_by_segment, ignore_index=True)
    regular = team_standings[team_standings["segment"].eq("regular_season")].copy()
    weekly_expected, season_expected = calculate_expected_wins(
        inputs["team_scores"], inputs["matchups"]
    )
    finishes = calculate_season_finishes(inputs["season_teams"], inputs["seasons"], facts)
    manager_segments = []
    for segment in team_standings["segment"].drop_duplicates():
        segment_standings = team_standings[team_standings["segment"].eq(segment)]
        manager_segments.append(
            build_manager_seasons(
                segment_standings,
                inputs["assignments"],
                expected_wins=season_expected if segment == "regular_season" else None,
                finishes=finishes,
            )
        )
    manager_seasons = (
        pd.concat(manager_segments, ignore_index=True)
        if manager_segments
        else build_manager_seasons(team_standings, inputs["assignments"])
    )
    manager_careers = summarize_manager_careers(manager_seasons)
    attributed = attribute_matchup_facts(facts, inputs["assignments"])
    head_to_head = summarize_head_to_head(
        attributed,
        segment="combined",
        entity_column="manager_id",
        opponent_column="opponent_manager_id",
    )
    streaks = calculate_streaks(facts, segment="combined")
    records = build_record_holders(
        facts,
        team_standings=regular,
        streaks=streaks,
        manager_careers=manager_careers,
        manager_seasons=manager_seasons,
        attributed_facts=attributed,
    )
    warnings = tuple(
        f"Season {int(row.season)} is active; finish and incomplete-game analytics remain partial."
        for row in inputs["seasons"].itertuples(index=False)
        if bool(row.is_active)
    )
    frames = {
        "matchup_facts": facts,
        "team_standings": team_standings,
        "season_finishes": finishes,
        "weekly_expected_wins": weekly_expected,
        "expected_wins": season_expected,
        "manager_seasons": manager_seasons,
        "manager_careers": manager_careers,
        "head_to_head": head_to_head,
        "streaks": streaks,
        "record_holders": records,
    }
    validate_analytics_frames(frames)
    return AnalyticsBuildResult(frames=frames, warnings=warnings)


def validate_analytics_frames(frames: dict[str, pd.DataFrame]) -> None:
    """Reject duplicate facts, untraceable records, and asymmetric rivalry totals."""
    facts = frames["matchup_facts"]
    fact_key = ["league_id", "season", "source_matchup_id", "source_team_id"]
    if facts.duplicated(fact_key).any():
        raise AnalyticsValidationError("Completed matchup facts are not unique.")
    if facts["source_row_key"].isna().any():
        raise AnalyticsValidationError("A completed matchup fact lacks source traceability.")
    available_records = frames["record_holders"][
        frames["record_holders"]["availability"].eq("available")
    ]
    if available_records["source_row_keys_json"].eq("[]").any():
        raise AnalyticsValidationError("An available record lacks source traceability.")
    head = frames["head_to_head"]
    if not head.empty:
        reverse = head.rename(
            columns={
                "manager_id": "opponent_manager_id",
                "opponent_manager_id": "manager_id",
                "wins": "reverse_losses",
                "losses": "reverse_wins",
                "ties": "reverse_ties",
                "points_for": "reverse_points_against",
                "points_against": "reverse_points_for",
            }
        )
        checked = head.merge(
            reverse[
                [
                    "manager_id",
                    "opponent_manager_id",
                    "reverse_wins",
                    "reverse_losses",
                    "reverse_ties",
                    "reverse_points_for",
                    "reverse_points_against",
                ]
            ],
            on=["manager_id", "opponent_manager_id"],
            how="left",
            validate="one_to_one",
        )
        balanced = (
            checked["wins"].eq(checked["reverse_wins"])
            & checked["losses"].eq(checked["reverse_losses"])
            & checked["ties"].eq(checked["reverse_ties"])
            & checked["points_for"].eq(checked["reverse_points_for"])
            & checked["points_against"].eq(checked["reverse_points_against"])
        )
        if not balanced.all():
            raise AnalyticsValidationError("Head-to-head totals do not reconcile.")


def _write_bundle(
    result: AnalyticsBuildResult,
    *,
    destination: Path,
    processed_root: Path,
    identities_root: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name, frame in result.frames.items():
        frame.to_parquet(destination / f"{name}.parquet", index=False, compression="zstd")
    manifest = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "formula_version": FORMULA_VERSION,
        "attribution_policy_version": ATTRIBUTION_POLICY_VERSION,
        "processed_source_checksums": {
            name: _checksum(processed_root / f"{name}.parquet") for name in PROCESSED_INPUTS
        },
        "identity_manifest_checksum": _checksum(identities_root / "manifest.json"),
        "row_counts": {name: len(frame) for name, frame in result.frames.items()},
        "coverage_warnings": list(result.warnings),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def rebuild_analytics(
    *,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    identities_root: Path = DEFAULT_IDENTITIES_ROOT,
    analytics_root: Path = DEFAULT_ANALYTICS_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> AnalyticsBuildResult:
    """Build, validate, and atomically promote the complete analytics bundle."""
    inputs, _ = _load_inputs(processed_root, identities_root)
    result = build_analytics_frames(inputs)
    transaction = staging_root / f"analytics-{uuid.uuid4().hex}"
    staged = transaction / "analytics"
    backup = transaction / "backup"
    transaction.mkdir(parents=True, exist_ok=False)
    try:
        _write_bundle(
            result,
            destination=staged,
            processed_root=processed_root,
            identities_root=identities_root,
        )
        try:
            if analytics_root.exists():
                analytics_root.replace(backup)
            staged.replace(analytics_root)
        except Exception:
            if analytics_root.exists():
                shutil.rmtree(analytics_root)
            if backup.exists():
                backup.replace(analytics_root)
            raise
        return result
    finally:
        shutil.rmtree(transaction, ignore_errors=True)


def analytics_bundle_is_current(
    *,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    identities_root: Path = DEFAULT_IDENTITIES_ROOT,
    analytics_root: Path = DEFAULT_ANALYTICS_ROOT,
) -> bool:
    """Return whether formula, source, and identity checksums match the bundle manifest."""
    try:
        manifest = json.loads((analytics_root / "manifest.json").read_text())
        return (
            manifest["analytics_schema_version"] == ANALYTICS_SCHEMA_VERSION
            and manifest["formula_version"] == FORMULA_VERSION
            and manifest["attribution_policy_version"] == ATTRIBUTION_POLICY_VERSION
            and manifest["identity_manifest_checksum"]
            == _checksum(identities_root / "manifest.json")
            and manifest["processed_source_checksums"]
            == {name: _checksum(processed_root / f"{name}.parquet") for name in PROCESSED_INPUTS}
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return False

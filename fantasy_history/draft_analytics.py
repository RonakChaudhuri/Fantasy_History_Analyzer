"""Versioned, atomic orchestration for Phase 6 draft-value analytics."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fantasy_history.draft_value import (
    BOOM_THRESHOLD,
    BUST_THRESHOLD,
    DRAFT_VALUE_FORMULA_VERSION,
    EXPECTED_MIN_SAMPLE,
    EXPECTED_PICK_WINDOW,
    LATE_ROUND_START,
    SLEEPER_THRESHOLD,
    build_draft_report_cards,
    build_player_history,
    calculate_draft_pick_values,
    enrich_draft_picks,
    summarize_position_allocation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
DEFAULT_IDENTITIES_ROOT = PROJECT_ROOT / "data" / "derived" / "identities"
DEFAULT_DRAFT_ANALYTICS_ROOT = PROJECT_ROOT / "data" / "derived" / "draft_analytics"
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "data" / ".staging"
DRAFT_ANALYTICS_SCHEMA_VERSION = "phase6.v1"

PROCESSED_INPUTS = (
    "seasons",
    "season_teams",
    "players",
    "drafts",
    "draft_picks",
    "player_scores",
    "roster_snapshots",
    "roster_players",
)
DRAFT_ANALYTICS_TABLES = (
    "replacement_baselines",
    "draft_pick_values",
    "draft_position_tendencies",
    "repeated_players",
    "draft_report_cards",
)


class DraftAnalyticsValidationError(RuntimeError):
    """A safe draft-analytics input, integrity, or promotion failure."""


@dataclass(frozen=True)
class DraftAnalyticsBuildResult:
    """Frames and non-private warnings produced by one draft analytics build."""

    frames: dict[str, pd.DataFrame]
    warnings: tuple[str, ...]


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_inputs(processed_root: Path, identities_root: Path) -> dict[str, pd.DataFrame]:
    try:
        inputs = {
            name: pd.read_parquet(processed_root / f"{name}.parquet") for name in PROCESSED_INPUTS
        }
        inputs["assignments"] = pd.read_parquet(
            identities_root / "manager_team_assignments.parquet"
        )
        identity_manifest = json.loads((identities_root / "manifest.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DraftAnalyticsValidationError(
            "Processed draft inputs or the identity bundle are unavailable."
        ) from exc
    counts = identity_manifest.get("counts", {})
    if not isinstance(counts, dict) or (
        counts.get("unresolved_teams") != 0
        or counts.get("conflict_count") != 0
        or counts.get("resolved_teams") != counts.get("total_teams")
    ):
        raise DraftAnalyticsValidationError("The identity bundle is incomplete.")
    return inputs


def build_draft_analytics_frames(inputs: dict[str, pd.DataFrame]) -> DraftAnalyticsBuildResult:
    """Build every Phase 6 draft output from injected normalized inputs."""
    picks = enrich_draft_picks(
        inputs["draft_picks"],
        inputs["players"],
        inputs["season_teams"],
        inputs["assignments"],
    )
    values, baselines = calculate_draft_pick_values(
        picks,
        inputs["player_scores"],
        inputs["players"],
        inputs["seasons"],
        inputs["season_teams"],
    )
    values = values.drop(columns=["source_member_id"], errors="ignore")
    frames = {
        "replacement_baselines": baselines,
        "draft_pick_values": values,
        "draft_position_tendencies": summarize_position_allocation(picks),
        "repeated_players": build_player_history(picks),
        "draft_report_cards": build_draft_report_cards(values),
    }
    validate_draft_analytics_frames(frames)
    warnings = (
        "Undrafted sleeper attribution is unavailable because retained roster snapshots lack "
        "acquisition type.",
        "Active-season picks and picks without actual season totals remain ineligible.",
    )
    return DraftAnalyticsBuildResult(frames=frames, warnings=warnings)


def validate_draft_analytics_frames(frames: dict[str, pd.DataFrame]) -> None:
    """Reject duplicate picks, unsupported labels, and non-reproducible report cards."""
    values = frames["draft_pick_values"]
    if values["source_row_key"].isna().any() or values["source_row_key"].duplicated().any():
        raise DraftAnalyticsValidationError("Draft value rows are not uniquely source-traceable.")
    unavailable = ~values["value_eligibility"].eq("eligible")
    if values.loc[unavailable, "value_label"].ne("unavailable").any():
        raise DraftAnalyticsValidationError("An ineligible pick received a value label.")
    if values.loc[unavailable, "normalized_surplus"].notna().any():
        raise DraftAnalyticsValidationError("An ineligible pick received normalized surplus.")
    allowed_labels = {"boom", "bust", "sleeper", "neutral", "unavailable"}
    if not set(values["value_label"].dropna()).issubset(allowed_labels):
        raise DraftAnalyticsValidationError("Draft value rows contain an unknown label.")
    baselines = frames["replacement_baselines"]
    if baselines.duplicated(["league_id", "season", "position"]).any():
        raise DraftAnalyticsValidationError("Replacement baselines are not unique.")
    cards = frames["draft_report_cards"]
    if not cards.empty and cards.duplicated(["league_id", "season", "canonical_manager_id"]).any():
        raise DraftAnalyticsValidationError("Draft report cards are not unique.")


def _thresholds() -> dict[str, object]:
    return {
        "boom_normalized_surplus": BOOM_THRESHOLD,
        "bust_normalized_surplus": BUST_THRESHOLD,
        "sleeper_normalized_surplus": SLEEPER_THRESHOLD,
        "late_round_start": LATE_ROUND_START,
        "expected_pick_window": EXPECTED_PICK_WINDOW,
        "expected_min_sample": EXPECTED_MIN_SAMPLE,
        "report_card_grade_bands": {"A": 80, "B": 65, "C": 50, "D": 35},
    }


def _write_bundle(
    result: DraftAnalyticsBuildResult,
    *,
    destination: Path,
    processed_root: Path,
    identities_root: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name, frame in result.frames.items():
        frame.to_parquet(destination / f"{name}.parquet", index=False, compression="zstd")
    manifest = {
        "draft_analytics_schema_version": DRAFT_ANALYTICS_SCHEMA_VERSION,
        "formula_version": DRAFT_VALUE_FORMULA_VERSION,
        "thresholds": _thresholds(),
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


def rebuild_draft_analytics(
    *,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    identities_root: Path = DEFAULT_IDENTITIES_ROOT,
    draft_analytics_root: Path = DEFAULT_DRAFT_ANALYTICS_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> DraftAnalyticsBuildResult:
    """Build, validate, and atomically promote the complete draft analytics bundle."""
    result = build_draft_analytics_frames(_load_inputs(processed_root, identities_root))
    transaction = staging_root / f"draft-analytics-{uuid.uuid4().hex}"
    staged = transaction / "draft_analytics"
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
            if draft_analytics_root.exists():
                draft_analytics_root.replace(backup)
            staged.replace(draft_analytics_root)
        except Exception:
            if draft_analytics_root.exists():
                shutil.rmtree(draft_analytics_root)
            if backup.exists():
                backup.replace(draft_analytics_root)
            raise
        return result
    finally:
        shutil.rmtree(transaction, ignore_errors=True)


def draft_analytics_bundle_is_current(
    *,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    identities_root: Path = DEFAULT_IDENTITIES_ROOT,
    draft_analytics_root: Path = DEFAULT_DRAFT_ANALYTICS_ROOT,
) -> bool:
    """Return whether formulas, thresholds, inputs, and identity checksums are current."""
    try:
        manifest = json.loads((draft_analytics_root / "manifest.json").read_text())
        return (
            all(
                (draft_analytics_root / f"{name}.parquet").is_file()
                for name in DRAFT_ANALYTICS_TABLES
            )
            and manifest["draft_analytics_schema_version"] == DRAFT_ANALYTICS_SCHEMA_VERSION
            and manifest["formula_version"] == DRAFT_VALUE_FORMULA_VERSION
            and manifest["thresholds"] == _thresholds()
            and manifest["processed_source_checksums"]
            == {name: _checksum(processed_root / f"{name}.parquet") for name in PROCESSED_INPUTS}
            and manifest["identity_manifest_checksum"]
            == _checksum(identities_root / "manifest.json")
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return False

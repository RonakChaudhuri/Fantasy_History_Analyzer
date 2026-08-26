from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from fantasy_history.analytics import ANALYTICS_SCHEMA_VERSION, PROCESSED_INPUTS
from fantasy_history.data_access import (
    REQUIRED_ANALYTICS_TABLES,
    REQUIRED_IDENTITY_TABLES,
    inspect_data_readiness,
)
from fantasy_history.formatting import (
    format_integer,
    format_percentage,
    format_points,
    format_record,
    format_signed,
)
from fantasy_history.standings import ATTRIBUTION_POLICY_VERSION, FORMULA_VERSION
from fantasy_history.ui import standings_for_segment


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path, *, warnings: list[str] | None = None) -> tuple[Path, Path, Path]:
    processed = root / "processed"
    identities = root / "identities"
    analytics = root / "analytics"
    for directory in (processed, identities, analytics):
        directory.mkdir()
    placeholder = pd.DataFrame({"fixture": pd.Series(dtype="string")})
    for name in (*PROCESSED_INPUTS, "managers"):
        placeholder.to_parquet(processed / f"{name}.parquet", index=False)
    for name in REQUIRED_IDENTITY_TABLES:
        placeholder.to_parquet(identities / f"{name}.parquet", index=False)
    identity_manifest = {
        "counts": {
            "total_teams": 2,
            "resolved_teams": 2,
            "unresolved_teams": 0,
            "conflict_count": 0,
        }
    }
    (identities / "manifest.json").write_text(json.dumps(identity_manifest), encoding="utf-8")
    for name in REQUIRED_ANALYTICS_TABLES:
        placeholder.to_parquet(analytics / f"{name}.parquet", index=False)
    manifest = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "formula_version": FORMULA_VERSION,
        "attribution_policy_version": ATTRIBUTION_POLICY_VERSION,
        "identity_manifest_checksum": _checksum(identities / "manifest.json"),
        "processed_source_checksums": {
            name: _checksum(processed / f"{name}.parquet") for name in PROCESSED_INPUTS
        },
        "coverage_warnings": warnings or [],
    }
    (analytics / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return processed, identities, analytics


def test_readiness_reports_missing_bundle(tmp_path: Path) -> None:
    state = inspect_data_readiness(
        processed_root=tmp_path / "processed",
        identities_root=tmp_path / "identities",
        analytics_root=tmp_path / "analytics",
    )

    assert state.status == "missing"
    assert not state.ready


def test_readiness_reports_current_partial_and_stale(tmp_path: Path) -> None:
    processed, identities, analytics = _write_bundle(tmp_path, warnings=["Season 2030 is active."])
    partial = inspect_data_readiness(
        processed_root=processed, identities_root=identities, analytics_root=analytics
    )

    assert partial.status == "partial"
    assert partial.ready
    assert partial.warnings == ("Season 2030 is active.",)

    manifest_path = analytics / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage_warnings"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    current = inspect_data_readiness(
        processed_root=processed, identities_root=identities, analytics_root=analytics
    )

    assert current.status == "current"
    assert current.ready

    manifest["formula_version"] = "stale"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    stale = inspect_data_readiness(
        processed_root=processed, identities_root=identities, analytics_root=analytics
    )

    assert stale.status == "stale"
    assert not stale.ready


def test_segment_standings_preserve_ties_shared_credit_and_nulls() -> None:
    seasons = pd.DataFrame(
        [
            {
                "canonical_manager_id": "manager-a",
                "canonical_display_name": "Manager A",
                "season": 2024,
                "segment": "championship_playoff",
                "wins": 1,
                "losses": 0,
                "ties": 1,
                "points_for": 210.0,
                "points_against": 200.0,
                "championship": True,
                "runner_up": False,
                "playoff_appearance": True,
                "official_finish": 1.0,
                "expected_wins": pd.NA,
                "luck_differential": pd.NA,
                "shared_attribution": True,
            }
        ]
    )

    result = standings_for_segment(seasons, "championship_playoff").iloc[0]

    assert result["win_percentage"] == 0.75
    assert result["playoff_wins"] == 1
    assert bool(result["shared_credit"])
    assert pd.isna(result["expected_wins"])
    assert pd.isna(result["average_finish"])


def test_phase5_formatters_do_not_turn_missing_values_into_zero() -> None:
    assert format_points(None) == "Unavailable"
    assert format_percentage(float("nan")) == "Unavailable"
    assert format_integer(None) == "Unavailable"
    assert format_signed(None) == "Unavailable"
    assert format_record(1, None, 0) == "Unavailable"
    assert format_record(8, 5, 1) == "8-5-1"
    assert format_signed(-1.25) == "-1.25"

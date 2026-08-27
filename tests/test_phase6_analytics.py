from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import fantasy_history.draft_analytics as draft_module
from fantasy_history.draft_analytics import (
    DRAFT_ANALYTICS_SCHEMA_VERSION,
    DRAFT_ANALYTICS_TABLES,
    PROCESSED_INPUTS,
    DraftAnalyticsBuildResult,
    draft_analytics_bundle_is_current,
    rebuild_draft_analytics,
)
from fantasy_history.draft_value import (
    DRAFT_VALUE_FORMULA_VERSION,
    build_draft_report_cards,
    calculate_replacement_baselines,
    classify_draft_values,
)


def test_flex_replacement_demand_uses_highest_remaining_positions() -> None:
    seasons = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "is_active": False,
                "lineup_slot_counts_json": json.dumps({"2": 1, "4": 1, "23": 1}),
            }
        ]
    )
    teams = pd.DataFrame(
        [
            {"league_id": 1, "season": 2024, "source_team_id": 1},
            {"league_id": 1, "season": 2024, "source_team_id": 2},
        ]
    )
    pool = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "position": position,
                "actual_fantasy_points": points,
                "production_eligibility": "eligible",
            }
            for position, points in [
                ("RB", 100),
                ("RB", 90),
                ("RB", 80),
                ("RB", 70),
                ("WR", 95),
                ("WR", 85),
                ("WR", 75),
                ("WR", 65),
            ]
        ]
    )

    baselines = calculate_replacement_baselines(pool, seasons, teams).set_index("position")

    assert baselines.loc["RB", "replacement_rank"] == 3
    assert baselines.loc["RB", "replacement_points"] == 80
    assert baselines.loc["WR", "replacement_rank"] == 3
    assert baselines.loc["WR", "replacement_points"] == 75
    assert baselines.loc["TE", "baseline_eligibility"] == "insufficient_position_pool"


def test_classification_thresholds_are_reproducible_and_null_safe() -> None:
    values = pd.DataFrame(
        [
            {
                "value_eligibility": "eligible",
                "normalized_surplus": 1.0,
                "round": 1,
                "position_adjusted_value": 20,
            },
            {
                "value_eligibility": "eligible",
                "normalized_surplus": -1.0,
                "round": 2,
                "position_adjusted_value": -20,
            },
            {
                "value_eligibility": "eligible",
                "normalized_surplus": 0.75,
                "round": 10,
                "position_adjusted_value": 1,
            },
            {
                "value_eligibility": "missing_actual_season_total",
                "normalized_surplus": pd.NA,
                "round": 10,
                "position_adjusted_value": pd.NA,
            },
        ]
    )

    result = classify_draft_values(values)

    assert result["value_label"].tolist() == ["boom", "bust", "sleeper", "unavailable"]
    assert result["boom_threshold"].eq(1.0).all()
    assert result["bust_threshold"].eq(-1.0).all()


def test_report_card_rates_score_and_grade_reproduce_from_pick_rows() -> None:
    values = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "canonical_manager_id": "a",
                "manager_name": "A",
                "source_pick_id": 1,
                "value_eligibility": "eligible",
                "raw_surplus": 40.0,
                "normalized_surplus": 1.5,
                "value_label": "boom",
            },
            {
                "league_id": 1,
                "season": 2024,
                "canonical_manager_id": "a",
                "manager_name": "A",
                "source_pick_id": 2,
                "value_eligibility": "eligible",
                "raw_surplus": 30.0,
                "normalized_surplus": 1.0,
                "value_label": "sleeper",
            },
            {
                "league_id": 1,
                "season": 2024,
                "canonical_manager_id": "b",
                "manager_name": "B",
                "source_pick_id": 3,
                "value_eligibility": "eligible",
                "raw_surplus": 20.0,
                "normalized_surplus": -0.5,
                "value_label": "neutral",
            },
            {
                "league_id": 1,
                "season": 2024,
                "canonical_manager_id": "b",
                "manager_name": "B",
                "source_pick_id": 4,
                "value_eligibility": "eligible",
                "raw_surplus": 10.0,
                "normalized_surplus": -1.5,
                "value_label": "bust",
            },
        ]
    )

    cards = build_draft_report_cards(values).set_index("canonical_manager_id")

    assert cards.loc["a", "boom_rate"] == 0.5
    assert cards.loc["a", "steal_rate"] == 1.0
    assert cards.loc["a", "report_card_score"] == 100.0
    assert cards.loc["a", "grade"] == "A"
    assert cards.loc["b", "bust_rate"] == 0.5
    assert cards.loc["b", "report_card_score"] == 50.0
    assert cards.loc["b", "grade"] == "C"


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_currentness_invalidates_changed_thresholds(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    identities = tmp_path / "identities"
    derived = tmp_path / "draft"
    for root in (processed, identities, derived):
        root.mkdir()
    for name in PROCESSED_INPUTS:
        (processed / f"{name}.parquet").write_bytes(name.encode())
    for name in DRAFT_ANALYTICS_TABLES:
        (derived / f"{name}.parquet").write_bytes(name.encode())
    (identities / "manifest.json").write_text("{}", encoding="utf-8")
    manifest = {
        "draft_analytics_schema_version": DRAFT_ANALYTICS_SCHEMA_VERSION,
        "formula_version": DRAFT_VALUE_FORMULA_VERSION,
        "thresholds": draft_module._thresholds(),
        "processed_source_checksums": {
            name: _checksum(processed / f"{name}.parquet") for name in PROCESSED_INPUTS
        },
        "identity_manifest_checksum": _checksum(identities / "manifest.json"),
    }
    path = derived / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert draft_analytics_bundle_is_current(
        processed_root=processed,
        identities_root=identities,
        draft_analytics_root=derived,
    )
    manifest["thresholds"]["boom_normalized_surplus"] = 9
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert not draft_analytics_bundle_is_current(
        processed_root=processed,
        identities_root=identities,
        draft_analytics_root=derived,
    )


def test_failed_draft_bundle_promotion_restores_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "draft"
    destination.mkdir()
    (destination / "old.txt").write_text("old", encoding="utf-8")
    fake = DraftAnalyticsBuildResult(frames={"sample": pd.DataFrame({"x": [1]})}, warnings=())
    monkeypatch.setattr(draft_module, "_load_inputs", lambda *_args: {})
    monkeypatch.setattr(draft_module, "build_draft_analytics_frames", lambda _inputs: fake)

    def fake_write(
        _result: DraftAnalyticsBuildResult,
        *,
        destination: Path,
        processed_root: Path,
        identities_root: Path,
    ) -> None:
        del processed_root, identities_root
        destination.mkdir(parents=True)
        (destination / "new.txt").write_text("new", encoding="utf-8")

    monkeypatch.setattr(draft_module, "_write_bundle", fake_write)
    original_replace = Path.replace

    def fail_staged_replace(path: Path, target: Path) -> Path:
        if path.name == "draft_analytics":
            raise OSError("injected promotion failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_staged_replace)

    with pytest.raises(OSError, match="injected"):
        rebuild_draft_analytics(
            processed_root=tmp_path / "processed",
            identities_root=tmp_path / "identities",
            draft_analytics_root=destination,
            staging_root=tmp_path / "staging",
        )

    assert (destination / "old.txt").read_text(encoding="utf-8") == "old"

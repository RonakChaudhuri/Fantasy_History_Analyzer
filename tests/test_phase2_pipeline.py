from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import fantasy_history.importer as importer_module
from fantasy_history.config import load_settings
from fantasy_history.importer import (
    ImportPipelineError,
    build_processed,
    import_seasons,
    load_season_snapshot,
    rebuild_processed,
    stage_season_snapshot,
)
from fantasy_history.normalization import TABLE_SCHEMAS, combine_tables, normalize_season

FIXTURE = Path(__file__).parent / "fixtures" / "phase2_season.json"


def load_fixture():
    return json.loads(FIXTURE.read_text())


def test_normalization_preserves_ties_byes_playoffs_and_source_traceability() -> None:
    tables = normalize_season(league_id=999, season=2019, payloads=load_fixture())
    frames = combine_tables([tables])

    assert frames["matchups"]["is_bye"].tolist() == [False, True]
    assert pd.isna(frames["matchups"].iloc[1]["scoring_period"])
    assert frames["team_scores"]["result"].tolist()[:2] == ["T", "T"]
    assert frames["team_scores"]["result"].iloc[2:].isna().all()
    assert len(frames["playoff_results"]) == 1
    assert frames["draft_picks"].iloc[0]["source_member_id"] == "member-a"
    for frame in frames.values():
        assert (
            list(frame.columns)
            == TABLE_SCHEMAS[
                next(name for name, candidate in frames.items() if candidate is frame)
            ].names
        )
        if not frame.empty:
            assert frame["source_file"].notna().all()
            assert frame["source_row_key"].is_unique


def test_snapshot_strips_private_notifications_and_rebuild_is_equivalent(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    season_root = raw_root / "2019"
    payloads = load_fixture()
    manifest = stage_season_snapshot(
        league_id=999,
        season=2019,
        payloads=payloads,
        routes=["historical"] * len(payloads),
        destination=season_root,
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert manifest.coverage["lineups"].status == "complete"
    assert manifest.coverage["schedule"].status == "complete"
    assert manifest.coverage["drafts"].status == "complete"
    assert "league.json" in manifest.source_shapes
    assert "$.settings:object" in manifest.source_shapes["league.json"]
    assert "notificationSettings" not in (season_root / "league.json").read_text()

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = build_processed([season_root], output_root=first_root)
    second = rebuild_processed(
        raw_root=raw_root, processed_root=second_root, staging_root=tmp_path / "staging"
    )
    for name in TABLE_SCHEMAS:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_corrupt_snapshot_is_rejected_without_replacing_processed(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    stage_season_snapshot(
        league_id=999,
        season=2019,
        payloads=load_fixture(),
        routes=["current"] * len(load_fixture()),
        destination=raw_root / "2019",
    )
    processed = tmp_path / "processed"
    rebuild_processed(raw_root=raw_root, processed_root=processed, staging_root=tmp_path / "stage")
    before = {path.name: path.read_bytes() for path in processed.glob("*.parquet")}
    (raw_root / "2019" / "league.json").write_text("{}")

    with pytest.raises(ImportPipelineError, match="checksum"):
        rebuild_processed(
            raw_root=raw_root, processed_root=processed, staging_root=tmp_path / "stage"
        )

    assert before == {path.name: path.read_bytes() for path in processed.glob("*.parquet")}


class FakeClient:
    def __init__(self, payloads, fail_section=None):
        self.payloads = payloads
        self.fail_section = fail_section
        self.settings = SimpleNamespace(league_id=999)

    def fetch(self, season, views, extra_params=None):
        if views == ("mSettings", "mTeam", "mNav"):
            key = "league"
        elif views == ("mMatchup", "mMatchupScore"):
            key = "schedule"
        elif views == ("mDraftDetail",):
            key = "draft"
        elif views == ("mRoster",):
            key = "rosters"
        else:
            key = f"lineups_{extra_params['scoringPeriodId']}"
            if key not in self.payloads:
                return {"schedule": []}, "current"
        if key == self.fail_section:
            raise RuntimeError("injected fetch failure")
        return self.payloads[key], "current"


def test_failed_refresh_preserves_previous_raw_and_processed_data(tmp_path: Path) -> None:
    settings = load_settings(
        env={
            "ESPN_LEAGUE_ID": "999",
            "ESPN_S2": "synthetic-secret",
            "ESPN_SWID": "{synthetic-swid}",
        }
    )
    raw_root = tmp_path / "raw"
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    fixture = load_fixture()
    import_seasons(
        settings,
        [2019],
        client=FakeClient(fixture),
        raw_root=raw_root,
        processed_root=processed,
        staging_root=staging,
    )
    raw_before = (raw_root / "2019" / "league.json").read_bytes()
    processed_before = {path.name: path.read_bytes() for path in processed.glob("*.parquet")}

    with pytest.raises(RuntimeError, match="injected"):
        import_seasons(
            settings,
            [2019],
            client=FakeClient(fixture, fail_section="draft"),
            raw_root=raw_root,
            processed_root=processed,
            staging_root=staging,
        )

    assert (raw_root / "2019" / "league.json").read_bytes() == raw_before
    assert {
        path.name: path.read_bytes() for path in processed.glob("*.parquet")
    } == processed_before


def test_validation_failure_preserves_previous_dataset(tmp_path: Path) -> None:
    settings = load_settings(
        env={"ESPN_LEAGUE_ID": "999", "ESPN_S2": "secret", "ESPN_SWID": "{swid}"}
    )
    fixture = load_fixture()
    raw_root, processed, staging = tmp_path / "raw", tmp_path / "processed", tmp_path / "stage"
    import_seasons(
        settings,
        [2019],
        client=FakeClient(fixture),
        raw_root=raw_root,
        processed_root=processed,
        staging_root=staging,
    )
    before = (raw_root / "2019" / "manifest.json").read_bytes()
    invalid = {**fixture, "draft": {}}

    with pytest.raises(Exception, match="draftDetail"):
        import_seasons(
            settings,
            [2019],
            client=FakeClient(invalid),
            raw_root=raw_root,
            processed_root=processed,
            staging_root=staging,
        )

    assert (raw_root / "2019" / "manifest.json").read_bytes() == before


def test_write_failure_preserves_previous_dataset(tmp_path: Path, monkeypatch) -> None:
    settings = load_settings(
        env={"ESPN_LEAGUE_ID": "999", "ESPN_S2": "secret", "ESPN_SWID": "{swid}"}
    )
    fixture = load_fixture()
    raw_root, processed, staging = tmp_path / "raw", tmp_path / "processed", tmp_path / "stage"
    import_seasons(
        settings,
        [2019],
        client=FakeClient(fixture),
        raw_root=raw_root,
        processed_root=processed,
        staging_root=staging,
    )
    before = (raw_root / "2019" / "manifest.json").read_bytes()

    def fail_write(_path, _value):
        raise OSError("injected write failure")

    monkeypatch.setattr(importer_module, "_write_json", fail_write)
    with pytest.raises(OSError, match="injected"):
        import_seasons(
            settings,
            [2019],
            client=FakeClient(fixture),
            raw_root=raw_root,
            processed_root=processed,
            staging_root=staging,
        )

    assert (raw_root / "2019" / "manifest.json").read_bytes() == before


def test_promotion_failure_rolls_back_raw_and_processed(tmp_path: Path, monkeypatch) -> None:
    raw_root, processed = tmp_path / "raw", tmp_path / "processed"
    (raw_root / "2019").mkdir(parents=True)
    (raw_root / "2019" / "old.txt").write_text("old raw")
    processed.mkdir()
    (processed / "old.txt").write_text("old processed")
    transaction = tmp_path / "transaction"
    staged_season = transaction / "raw" / "2019"
    staged_season.mkdir(parents=True)
    (staged_season / "new.txt").write_text("new raw")
    staged_processed = transaction / "processed"
    staged_processed.mkdir()
    (staged_processed / "new.txt").write_text("new processed")
    original_replace = Path.replace

    def injected_replace(path, target):
        if path == staged_processed:
            raise OSError("injected promotion failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(OSError, match="injected"):
        importer_module._promote(
            staged_seasons={2019: staged_season},
            staged_processed=staged_processed,
            raw_root=raw_root,
            processed_root=processed,
            transaction_root=transaction,
        )

    assert (raw_root / "2019" / "old.txt").read_text() == "old raw"
    assert (processed / "old.txt").read_text() == "old processed"


def test_historical_manifest_list_envelope_is_validated(tmp_path: Path) -> None:
    payloads = load_fixture()
    destination = tmp_path / "2019"
    stage_season_snapshot(
        league_id=999,
        season=2019,
        payloads=payloads,
        routes=["historical"] * len(payloads),
        destination=destination,
    )
    manifest, loaded = load_season_snapshot(destination)
    assert manifest.route == "historical"
    assert set(loaded) == set(payloads)

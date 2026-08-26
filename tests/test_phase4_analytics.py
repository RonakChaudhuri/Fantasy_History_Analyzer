from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import fantasy_history.analytics as analytics_module
from fantasy_history.analytics import (
    AnalyticsValidationError,
    analytics_bundle_is_current,
    rebuild_analytics,
)
from fantasy_history.records import build_record_holders
from fantasy_history.rivalries import calculate_streaks, summarize_head_to_head
from fantasy_history.standings import (
    build_manager_seasons,
    build_matchup_facts,
    calculate_expected_wins,
    summarize_manager_careers,
    summarize_team_standings,
)


def matchup_frame() -> pd.DataFrame:
    base = {
        "league_id": 999,
        "season": 2019,
        "scoring_period": 1,
        "matchup_period": 1,
        "playoff_tier": "NONE",
        "is_playoff": False,
        "is_consolation": False,
        "is_bye": False,
        "source_file": "2019/matchups.json",
    }
    return pd.DataFrame(
        [
            {
                **base,
                "source_matchup_id": 1,
                "home_team_id": 1,
                "away_team_id": 2,
                "home_score": 100.0,
                "away_score": 100.0,
                "winner": "TIE",
                "source_row_key": "2019:matchup:1",
            },
            {
                **base,
                "source_matchup_id": 2,
                "home_team_id": 3,
                "away_team_id": 4,
                "home_score": 80.0,
                "away_score": 70.0,
                "winner": "HOME",
                "source_row_key": "2019:matchup:2",
            },
            {
                **base,
                "source_matchup_id": 3,
                "home_team_id": 1,
                "away_team_id": None,
                "home_score": 90.0,
                "away_score": None,
                "winner": "HOME",
                "is_bye": True,
                "source_row_key": "2019:matchup:3",
            },
            {
                **base,
                "source_matchup_id": 4,
                "home_team_id": 2,
                "away_team_id": 3,
                "home_score": 90.0,
                "away_score": None,
                "winner": "UNDECIDED",
                "source_row_key": "2019:matchup:4",
            },
            {
                **base,
                "source_matchup_id": 5,
                "scoring_period": None,
                "matchup_period": 2,
                "home_team_id": 1,
                "away_team_id": 3,
                "home_score": 110.0,
                "away_score": 90.0,
                "winner": "HOME",
                "playoff_tier": "WINNERS_BRACKET",
                "is_playoff": True,
                "source_row_key": "2019:matchup:5",
            },
            {
                **base,
                "source_matchup_id": 6,
                "matchup_period": 2,
                "home_team_id": 2,
                "away_team_id": 4,
                "home_score": 75.0,
                "away_score": 85.0,
                "winner": "AWAY",
                "playoff_tier": "LOSERS_CONSOLATION_LADDER",
                "is_playoff": True,
                "is_consolation": True,
                "source_row_key": "2019:matchup:6",
            },
        ]
    )


def test_standings_exclude_byes_missing_scores_and_split_segments() -> None:
    facts = build_matchup_facts(matchup_frame())
    assert len(facts) == 8
    assert set(facts["segment"]) == {
        "regular_season",
        "championship_playoff",
        "consolation",
    }
    assert facts[facts["source_matchup_id"].eq(5)]["scoring_period"].isna().all()

    regular = summarize_team_standings(facts)
    team_one = regular[regular["source_team_id"].eq(1)].iloc[0]
    assert (team_one.wins, team_one.losses, team_one.ties) == (0, 0, 1)
    assert team_one.win_percentage == 0.5
    assert team_one.point_differential == 0.0

    combined = summarize_team_standings(facts, segment="combined")
    team_one = combined[combined["source_team_id"].eq(1)].iloc[0]
    assert (team_one.wins, team_one.ties, team_one.completed_games) == (1, 1, 2)
    assert team_one.win_percentage == 0.75


def test_expected_wins_handle_ties_and_reduced_comparison_pool() -> None:
    matchups = matchup_frame().iloc[:2].copy()
    scores = pd.DataFrame(
        [
            (1, 2, 100.0, "T", "score:1"),
            (2, 1, 100.0, "T", "score:2"),
            (3, 4, 80.0, "W", "score:3"),
            (4, 3, 70.0, "L", "score:4"),
        ],
        columns=["source_team_id", "opponent_team_id", "points", "result", "source_row_key"],
    )
    scores = scores.assign(
        league_id=999,
        season=2019,
        source_matchup_id=[1, 1, 2, 2],
        scoring_period=1,
        side=["home", "away", "home", "away"],
        source_file="2019/matchups.json",
    )
    weekly, season = calculate_expected_wins(scores, matchups)
    shares = weekly.set_index("source_team_id")["expected_win_share"].to_dict()
    assert shares == pytest.approx({1: 5 / 6, 2: 5 / 6, 3: 1 / 3, 4: 0.0})
    assert season.set_index("source_team_id").loc[3, "luck_differential"] == pytest.approx(2 / 3)

    reduced = calculate_expected_wins(scores[scores["source_team_id"].ne(4)], matchups)[0]
    assert set(reduced["comparison_count"]) == {2}


def test_rivalries_reconcile_and_streaks_span_seasons_but_break_on_missing_coverage() -> None:
    facts = build_matchup_facts(matchup_frame())
    head = summarize_head_to_head(facts, segment="combined")
    one_two = head[(head.source_team_id == 1) & (head.opponent_team_id == 2)].iloc[0]
    two_one = head[(head.source_team_id == 2) & (head.opponent_team_id == 1)].iloc[0]
    assert one_two.wins == two_one.losses
    assert one_two.ties == two_one.ties == 1
    assert one_two.points_for == two_one.points_against

    streak_facts = pd.DataFrame(
        [
            (2019, 1, "W", False, "a"),
            (2019, 2, "W", False, "b"),
            (2020, 3, "W", False, "c"),
            (2020, 4, "W", True, "d"),
            (2020, 5, "W", False, "e"),
        ],
        columns=["season", "source_matchup_id", "result", "coverage_break", "source_row_key"],
    ).assign(
        source_team_id=1,
        segment="regular_season",
        matchup_period=[1, 2, 1, 2, 3],
    )
    streaks = calculate_streaks(streak_facts, coverage_break_column="coverage_break")
    win = streaks[streaks["result"].eq("W")].iloc[0]
    assert win.streak_length == 3
    assert (win.start_season, win.end_season) == (2019, 2020)


def test_manager_renames_and_shared_teams_remain_explicit() -> None:
    standings = pd.DataFrame(
        [
            (999, 2019, 1, "regular_season", 8, 5, 0, 13, 8 / 13, 1200.0, 1100.0, 100.0, "v"),
            (999, 2020, 7, "regular_season", 9, 4, 0, 13, 9 / 13, 1250.0, 1120.0, 130.0, "v"),
        ],
        columns=[
            "league_id",
            "season",
            "source_team_id",
            "segment",
            "wins",
            "losses",
            "ties",
            "completed_games",
            "win_percentage",
            "points_for",
            "points_against",
            "point_differential",
            "formula_version",
        ],
    )
    assignments = pd.DataFrame(
        [
            (999, 2019, 1, "manager-a", "Manager A", "single_owner"),
            (999, 2020, 7, "manager-a", "Manager A", "co_owner"),
            (999, 2020, 7, "manager-b", "Manager B", "co_owner"),
        ],
        columns=[
            "league_id",
            "season",
            "source_team_id",
            "canonical_manager_id",
            "canonical_display_name",
            "resolution_type",
        ],
    )
    expected = pd.DataFrame(
        [
            (999, 2019, 1, 13, 7.5, 8, 0.5, "v"),
            (999, 2020, 7, 13, 8.0, 9, 1.0, "v"),
        ],
        columns=[
            "league_id",
            "season",
            "source_team_id",
            "weeks_compared",
            "expected_wins",
            "actual_wins",
            "luck_differential",
            "formula_version",
        ],
    )
    finishes = pd.DataFrame(
        [
            (999, 2019, 1, 1, 1, True, True, False),
            (999, 2020, 7, 2, 2, True, False, True),
        ],
        columns=[
            "league_id",
            "season",
            "source_team_id",
            "playoff_seed",
            "official_finish",
            "playoff_appearance",
            "championship",
            "runner_up",
        ],
    )
    regular_seasons = build_manager_seasons(
        standings, assignments, expected_wins=expected, finishes=finishes
    )
    combined_seasons = regular_seasons.copy()
    combined_seasons["segment"] = "combined"
    playoff_standings = standings.copy()
    playoff_standings["segment"] = "championship_playoff"
    playoff_standings[["wins", "losses", "completed_games"]] = [[2, 0, 2], [1, 1, 2]]
    playoff_seasons = build_manager_seasons(playoff_standings, assignments, finishes=finishes)
    seasons = pd.concat([regular_seasons, combined_seasons, playoff_seasons], ignore_index=True)
    career = summarize_manager_careers(seasons)
    manager_a = career[career["canonical_manager_id"].eq("manager-a")].iloc[0]
    assert manager_a.seasons_played == 2
    assert manager_a.wins == 17
    assert manager_a.playoff_wins == 3
    assert manager_a.championships == 1
    assert manager_a.runner_up_finishes == 1
    assert manager_a.average_finish == 1.5
    assert manager_a.expected_wins == 15.5
    assert manager_a.luck_differential == 1.5
    assert bool(manager_a.contains_shared_attribution)
    assert seasons[seasons.canonical_manager_id.eq("manager-b")].shared_attribution.all()


def test_records_retain_tied_holders_and_exact_source_keys() -> None:
    facts = build_matchup_facts(matchup_frame())
    standings = summarize_team_standings(facts)
    records = build_record_holders(facts, team_standings=standings)
    high = records[records["category"].eq("highest_weekly_score")]
    assert len(high) == 1
    assert high.iloc[0].source_row_key == "2019:matchup:5"
    closest = records[records["category"].eq("closest_result")]
    assert len(closest) == 2
    assert closest["source_row_key"].notna().all()
    assert records[records["availability"].eq("available")]["source_row_keys_json"].ne("[]").all()


def _write_identity_bundle(processed: Path, identities: Path) -> None:
    teams = pd.read_parquet(processed / "season_teams.parquet")
    assignments = teams[["league_id", "season", "source_team_id"]].copy()
    assignments["source_team_row_key"] = teams["source_row_key"]
    assignments["source_file"] = teams["source_file"]
    assignments["primary_owner_id"] = None
    assignments["source_member_ids_json"] = "[]"
    assignments["canonical_manager_id"] = assignments["source_team_id"].map(
        lambda value: f"manager-{value}"
    )
    assignments["canonical_display_name"] = assignments["source_team_id"].map(
        lambda value: f"Manager {value}"
    )
    assignments["resolution_type"] = "single_owner"
    assignments["identity_schema_version"] = "phase3.v1"
    identities.mkdir(parents=True)
    assignments.to_parquet(identities / "manager_team_assignments.parquet", index=False)
    checksums = {
        name: hashlib.sha256((processed / f"{name}.parquet").read_bytes()).hexdigest()
        for name in ("managers", "season_teams")
    }
    (identities / "manifest.json").write_text(
        json.dumps(
            {
                "counts": {
                    "total_teams": len(teams),
                    "resolved_teams": len(teams),
                    "unresolved_teams": 0,
                    "conflict_count": 0,
                },
                "source_checksums": checksums,
            }
        )
    )


def test_atomic_rebuild_is_equivalent_and_checksum_changes_invalidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fantasy_history.importer import build_processed, stage_season_snapshot

    fixture_path = Path(__file__).parent / "fixtures" / "phase2_season.json"
    payloads = json.loads(fixture_path.read_text())
    raw = tmp_path / "raw" / "2019"
    stage_season_snapshot(
        league_id=999,
        season=2019,
        payloads=payloads,
        routes=["synthetic"] * len(payloads),
        destination=raw,
    )
    processed = tmp_path / "processed"
    identities = tmp_path / "identities"
    analytics = tmp_path / "analytics"
    build_processed([raw], output_root=processed)
    _write_identity_bundle(processed, identities)

    first = rebuild_analytics(
        processed_root=processed,
        identities_root=identities,
        analytics_root=analytics,
        staging_root=tmp_path / "stage",
    )
    second = rebuild_analytics(
        processed_root=processed,
        identities_root=identities,
        analytics_root=analytics,
        staging_root=tmp_path / "stage",
    )
    for name in first.frames:
        pd.testing.assert_frame_equal(first.frames[name], second.frames[name])
    assert {
        "most_championships",
        "most_runner_up_finishes",
        "most_playoff_appearances",
        "most_playoff_wins",
    }.issubset(set(first.frames["record_holders"]["category"]))
    assert analytics_bundle_is_current(
        processed_root=processed,
        identities_root=identities,
        analytics_root=analytics,
    )

    before = {path.name: path.read_bytes() for path in analytics.iterdir()}

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("injected analytics write failure")

    monkeypatch.setattr(analytics_module, "_write_bundle", fail_write)
    with pytest.raises(OSError, match="injected"):
        rebuild_analytics(
            processed_root=processed,
            identities_root=identities,
            analytics_root=analytics,
            staging_root=tmp_path / "stage",
        )
    assert before == {path.name: path.read_bytes() for path in analytics.iterdir()}

    monkeypatch.undo()
    scores = pd.read_parquet(processed / "team_scores.parquet")
    scores.loc[scores.index[0], "points"] += 0.01
    scores.to_parquet(processed / "team_scores.parquet", index=False)
    assert not analytics_bundle_is_current(
        processed_root=processed,
        identities_root=identities,
        analytics_root=analytics,
    )


def test_incomplete_identity_bundle_blocks_rebuild(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    identities = tmp_path / "identities"
    identities.mkdir()
    (identities / "manifest.json").write_text("{}")
    with pytest.raises(AnalyticsValidationError, match="unavailable"):
        rebuild_analytics(
            processed_root=processed,
            identities_root=identities,
            analytics_root=tmp_path / "analytics",
            staging_root=tmp_path / "stage",
        )

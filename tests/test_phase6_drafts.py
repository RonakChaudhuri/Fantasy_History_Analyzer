from __future__ import annotations

import pandas as pd

from fantasy_history.draft_value import (
    PRODUCTION_FORMULA_VERSION,
    attach_actual_production,
    attach_final_position_ranks,
    build_draft_board,
    build_player_history,
    enrich_draft_picks,
    production_coverage_by_season,
    select_completed_roster,
    summarize_position_allocation,
)


def _draft_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    picks = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_pick_id": 1,
                "overall_pick": 1,
                "round": 1,
                "round_pick": 1,
                "source_team_id": 10,
                "source_member_id": "private-a",
                "source_player_id": 101,
                "player_name": pd.NA,
                "bid_amount": 0.0,
                "is_keeper": False,
                "source_file": "2024/draft.json",
                "source_row_key": "2024:pick:1",
            },
            {
                "league_id": 1,
                "season": 2024,
                "source_pick_id": 2,
                "overall_pick": 2,
                "round": 1,
                "round_pick": 2,
                "source_team_id": 20,
                "source_member_id": "private-b",
                "source_player_id": 102,
                "player_name": pd.NA,
                "bid_amount": 0.0,
                "is_keeper": True,
                "source_file": "2024/draft.json",
                "source_row_key": "2024:pick:2",
            },
            {
                "league_id": 1,
                "season": 2024,
                "source_pick_id": 3,
                "overall_pick": 3,
                "round": 2,
                "round_pick": 1,
                "source_team_id": 20,
                "source_member_id": "private-b",
                "source_player_id": 103,
                "player_name": pd.NA,
                "bid_amount": 0.0,
                "is_keeper": False,
                "source_file": "2024/draft.json",
                "source_row_key": "2024:pick:3",
            },
            {
                "league_id": 1,
                "season": 2024,
                "source_pick_id": 4,
                "overall_pick": 4,
                "round": 2,
                "round_pick": 2,
                "source_team_id": 20,
                "source_member_id": "private-b",
                "source_player_id": 101,
                "player_name": pd.NA,
                "bid_amount": 0.0,
                "is_keeper": False,
                "source_file": "2024/draft.json",
                "source_row_key": "2024:pick:4",
            },
        ]
    )
    players = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": 101,
                "full_name": "Player One",
                "default_position_id": 2,
            },
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": 102,
                "full_name": "Player Two",
                "default_position_id": 1,
            },
        ]
    )
    teams = pd.DataFrame(
        [
            {"league_id": 1, "season": 2024, "source_team_id": 10, "team_name": "A"},
            {"league_id": 1, "season": 2024, "source_team_id": 20, "team_name": "B"},
        ]
    )
    assignments = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_team_id": 10,
                "canonical_manager_id": "manager-a",
                "canonical_display_name": "Manager A",
            },
            {
                "league_id": 1,
                "season": 2024,
                "source_team_id": 20,
                "canonical_manager_id": "manager-b",
                "canonical_display_name": "Manager B",
            },
        ]
    )
    return picks, players, teams, assignments


def test_draft_board_preserves_order_keepers_irregular_picks_and_nulls() -> None:
    picks, players, teams, assignments = _draft_inputs()
    enriched = enrich_draft_picks(picks, players, teams, assignments)
    board = build_draft_board(enriched, 2024)

    assert list(board.columns) == ["Round", "A", "B"]
    assert board.iloc[0]["A"] == "1. Player One"
    assert board.iloc[0]["B"] == "2. Player Two (keeper)"
    assert board.iloc[1]["B"] == "3. Unavailable player · 4. Player One"
    assert pd.isna(enriched.loc[enriched["source_player_id"].eq(103), "position"]).all()


def test_tendencies_use_only_known_positions_and_repeat_stable_player_ids() -> None:
    picks, players, teams, assignments = _draft_inputs()
    prior = picks.iloc[[0]].copy()
    prior["season"] = 2023
    prior["source_pick_id"] = 9
    prior["source_row_key"] = "2023:pick:9"
    prior_players = players.iloc[[0]].copy()
    prior_players["season"] = 2023
    prior_teams = teams[teams["source_team_id"].eq(10)].copy()
    prior_teams["season"] = 2023
    prior_assignments = assignments[assignments["source_team_id"].eq(10)].copy()
    prior_assignments["season"] = 2023
    enriched = enrich_draft_picks(
        pd.concat([prior, picks], ignore_index=True),
        pd.concat([prior_players, players], ignore_index=True),
        pd.concat([prior_teams, teams], ignore_index=True),
        pd.concat([prior_assignments, assignments], ignore_index=True),
    )
    enriched.loc[
        enriched["season"].eq(2023) & enriched["source_player_id"].eq(101), "player_name"
    ] = pd.NA

    allocation = summarize_position_allocation(enriched)
    history = build_player_history(enriched)

    assert allocation["picks"].sum() == 4
    repeated = history[
        history["canonical_manager_id"].eq("manager-a") & history["source_player_id"].eq(101)
    ].iloc[0]
    assert repeated["seasons_drafted"] == 2
    assert repeated["seasons"] == "2023, 2024"
    assert repeated["player_name"] == "Player One"


def test_actual_production_filters_projections_and_deduplicates_observations() -> None:
    picks, players, teams, assignments = _draft_inputs()
    enriched = enrich_draft_picks(picks, players, teams, assignments)
    score_rows = []
    for index, (player_id, source, scope, points) in enumerate(
        [
            (101, "actual", "season_total", 100.0),
            (101, "actual", "season_total", 100.0),
            (101, "projected", "season_total", 250.0),
            (101, "actual", "weekly", 12.0),
            (102, "actual", "season_total", 80.0),
            (102, "actual", "season_total", 81.0),
        ]
    ):
        score_rows.append(
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": player_id,
                "score_season": 2024,
                "stat_source": source,
                "score_scope": scope,
                "availability": "available",
                "applied_fantasy_points": points,
                "source_row_key": f"score:{index}",
            }
        )
    result = attach_actual_production(
        enriched,
        pd.DataFrame(score_rows),
        pd.DataFrame([{"season": 2024, "is_active": False}]),
    )

    player_one = result[result["source_player_id"].eq(101)]
    assert player_one["actual_fantasy_points"].eq(100.0).all()
    assert player_one["score_observation_count"].eq(2).all()
    assert player_one["production_eligibility"].eq("eligible").all()
    player_two = result[result["source_player_id"].eq(102)].iloc[0]
    assert player_two["production_eligibility"] == "conflicting_actual_season_totals"
    assert pd.isna(player_two["actual_fantasy_points"])
    assert result["production_formula_version"].eq(PRODUCTION_FORMULA_VERSION).all()
    coverage = production_coverage_by_season(result).iloc[0]
    assert coverage["total_picks"] == 4
    assert coverage["eligible_picks"] == 2
    assert coverage["eligible_share"] == 0.5


def test_active_season_production_is_ineligible_even_when_actual_total_exists() -> None:
    picks, players, teams, assignments = _draft_inputs()
    enriched = enrich_draft_picks(picks.iloc[[0]], players, teams, assignments)
    score = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": 101,
                "score_season": 2024,
                "stat_source": "actual",
                "score_scope": "season_total",
                "availability": "available",
                "applied_fantasy_points": 50.0,
                "source_row_key": "score:active",
            }
        ]
    )

    result = attach_actual_production(
        enriched, score, pd.DataFrame([{"season": 2024, "is_active": True}])
    ).iloc[0]

    assert result["production_eligibility"] == "active_season"
    assert pd.isna(result["actual_fantasy_points"])


def test_final_position_ranks_use_actual_season_points_and_preserve_missing() -> None:
    seasons = pd.DataFrame([{"season": 2024, "is_active": False}])
    players = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": player_id,
                "full_name": f"Player {player_id}",
                "default_position_id": 2,
            }
            for player_id in (101, 102, 103, 104)
        ]
    )
    scores = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "source_player_id": player_id,
                "score_season": 2024,
                "stat_source": "actual",
                "score_scope": "season_total",
                "availability": "available",
                "applied_fantasy_points": points,
                "source_row_key": f"score:{player_id}",
            }
            for player_id, points in ((101, 100.0), (102, 90.0), (103, 90.0))
        ]
    )
    roster = pd.DataFrame(
        [
            {"league_id": 1, "season": 2024, "source_player_id": player_id}
            for player_id in (101, 102, 104)
        ]
    )

    result = attach_final_position_ranks(roster, scores, players, seasons).set_index(
        "source_player_id"
    )

    assert result.loc[101, "final_position_rank"] == 1
    assert result.loc[102, "final_position_rank"] == 2
    assert pd.isna(result.loc[104, "final_position_rank"])


def test_final_roster_rejects_active_empty_and_missing_team_snapshots() -> None:
    _, _, teams, assignments = _draft_inputs()
    seasons = pd.DataFrame([{"season": 2024, "is_active": True}])
    snapshots = pd.DataFrame(
        [
            {
                "season": 2024,
                "snapshot_type": "season_roster",
                "source_team_id": 10,
                "coverage_status": "available-empty",
                "entry_count": 0,
            }
        ]
    )

    active = select_completed_roster(2024, seasons, snapshots, pd.DataFrame(), teams, assignments)
    assert active.status == "active_season"
    assert not active.available

    seasons.loc[0, "is_active"] = False
    missing = select_completed_roster(2024, seasons, snapshots, pd.DataFrame(), teams, assignments)
    assert missing.status == "missing_snapshot"


def test_final_roster_returns_source_traceable_completed_rows() -> None:
    _, _, teams, assignments = _draft_inputs()
    seasons = pd.DataFrame([{"season": 2024, "is_active": False}])
    snapshots = pd.DataFrame(
        [
            {
                "season": 2024,
                "snapshot_type": "season_roster",
                "source_team_id": team_id,
                "coverage_status": "complete",
                "entry_count": 1,
            }
            for team_id in (10, 20)
        ]
    )
    roster_players = pd.DataFrame(
        [
            {
                "league_id": 1,
                "season": 2024,
                "snapshot_type": "season_roster",
                "source_team_id": team_id,
                "source_player_id": team_id,
                "lineup_slot_id": 20,
                "player_name": f"Player {team_id}",
                "default_position_id": 2,
                "source_row_key": f"2024:roster:{team_id}",
            }
            for team_id in (10, 20)
        ]
    )

    result = select_completed_roster(2024, seasons, snapshots, roster_players, teams, assignments)

    assert result.available
    assert len(result.rows) == 2
    assert result.rows["source_row_key"].notna().all()
    assert set(result.rows["position"]) == {"RB"}

    snapshots.loc[snapshots["source_team_id"].eq(10), "entry_count"] = 2
    mismatch = select_completed_roster(2024, seasons, snapshots, roster_players, teams, assignments)
    assert mismatch.status == "incomplete_snapshot"

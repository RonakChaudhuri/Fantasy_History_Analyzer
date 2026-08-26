"""Pure, source-traceable standings, playoff, and expected-win analytics."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

FORMULA_VERSION = "phase4.v1"
ATTRIBUTION_POLICY_VERSION = "shared-credit.v1"

MATCHUP_FACT_COLUMNS = [
    "league_id",
    "season",
    "source_matchup_id",
    "scoring_period",
    "matchup_period",
    "segment",
    "source_team_id",
    "opponent_team_id",
    "points_for",
    "points_against",
    "result",
    "margin",
    "combined_points",
    "source_file",
    "source_row_key",
    "formula_version",
]
MANAGER_CAREER_COLUMNS = [
    "canonical_manager_id",
    "display_name",
    "seasons_played",
    "wins",
    "losses",
    "ties",
    "points_for",
    "points_against",
    "championships",
    "runner_up_finishes",
    "playoff_appearances",
    "playoff_wins",
    "playoff_losses",
    "playoff_ties",
    "average_finish",
    "best_finish",
    "worst_finish",
    "expected_wins",
    "luck_differential",
    "contains_shared_attribution",
    "win_percentage",
    "point_differential",
    "formula_version",
    "attribution_policy_version",
]


def _segment(row: Any) -> str:
    if bool(row.is_consolation):
        return "consolation"
    if bool(row.is_playoff):
        return "championship_playoff"
    tier = row.playoff_tier
    if pd.isna(tier) or str(tier) == "NONE":
        return "regular_season"
    return "unknown"


def _result(winner: str, side: str) -> str:
    if winner == "TIE":
        return "T"
    return "W" if winner == side.upper() else "L"


def build_matchup_facts(matchups: pd.DataFrame) -> pd.DataFrame:
    """Return two team-perspective rows per completed, non-bye matchup."""
    required = {
        "league_id",
        "season",
        "source_matchup_id",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "winner",
        "is_playoff",
        "is_consolation",
        "is_bye",
        "source_file",
        "source_row_key",
    }
    missing = required - set(matchups.columns)
    if missing:
        raise ValueError(f"Matchups are missing required columns: {sorted(missing)}")
    rows: list[dict[str, object]] = []
    for row in matchups.itertuples(index=False):
        complete = (
            not bool(row.is_bye)
            and pd.notna(row.home_team_id)
            and pd.notna(row.away_team_id)
            and pd.notna(row.home_score)
            and pd.notna(row.away_score)
            and row.winner in {"HOME", "AWAY", "TIE"}
        )
        if not complete:
            continue
        segment = _segment(row)
        for side, team, opponent, points, against in (
            ("home", row.home_team_id, row.away_team_id, row.home_score, row.away_score),
            ("away", row.away_team_id, row.home_team_id, row.away_score, row.home_score),
        ):
            rows.append(
                {
                    "league_id": int(row.league_id),
                    "season": int(row.season),
                    "source_matchup_id": int(row.source_matchup_id),
                    "scoring_period": (
                        int(row.scoring_period) if pd.notna(row.scoring_period) else None
                    ),
                    "matchup_period": (
                        int(row.matchup_period) if pd.notna(row.matchup_period) else None
                    ),
                    "segment": segment,
                    "source_team_id": int(team),
                    "opponent_team_id": int(opponent),
                    "points_for": float(points),
                    "points_against": float(against),
                    "result": _result(str(row.winner), side),
                    "margin": float(points) - float(against),
                    "combined_points": float(points) + float(against),
                    "source_file": str(row.source_file),
                    "source_row_key": str(row.source_row_key),
                    "formula_version": FORMULA_VERSION,
                }
            )
    frame = pd.DataFrame(rows, columns=MATCHUP_FACT_COLUMNS)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["season", "matchup_period", "source_matchup_id", "source_team_id"],
        na_position="last",
        ignore_index=True,
    )


def eligible_segments(segment: str) -> set[str]:
    choices = {
        "regular_season": {"regular_season"},
        "championship_playoff": {"championship_playoff"},
        "consolation": {"consolation"},
        "combined": {"regular_season", "championship_playoff"},
        "all": {"regular_season", "championship_playoff", "consolation", "unknown"},
    }
    if segment not in choices:
        raise ValueError(f"Unknown competition segment: {segment}")
    return choices[segment]


def summarize_team_standings(
    facts: pd.DataFrame, *, segment: str = "regular_season"
) -> pd.DataFrame:
    """Aggregate team-season records without converting unavailable games to zero."""
    selected = facts[facts["segment"].isin(eligible_segments(segment))].copy()
    columns = [
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
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected["wins"] = selected["result"].eq("W").astype("int64")
    selected["losses"] = selected["result"].eq("L").astype("int64")
    selected["ties"] = selected["result"].eq("T").astype("int64")
    grouped = (
        selected.groupby(["league_id", "season", "source_team_id"], as_index=False)
        .agg(
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            ties=("ties", "sum"),
            completed_games=("result", "size"),
            points_for=("points_for", "sum"),
            points_against=("points_against", "sum"),
        )
        .sort_values(["season", "source_team_id"], ignore_index=True)
    )
    grouped["segment"] = segment
    grouped["win_percentage"] = (grouped["wins"] + 0.5 * grouped["ties"]) / grouped[
        "completed_games"
    ]
    grouped["point_differential"] = grouped["points_for"] - grouped["points_against"]
    grouped["formula_version"] = FORMULA_VERSION
    return grouped[columns]


def calculate_expected_wins(
    team_scores: pd.DataFrame, matchups: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate weekly all-play shares and regular-season luck."""
    segment_keys = matchups[
        ["league_id", "season", "source_matchup_id", "is_playoff", "is_consolation"]
    ].drop_duplicates()
    scores = team_scores.merge(
        segment_keys,
        on=["league_id", "season", "source_matchup_id"],
        how="left",
        validate="many_to_one",
    )
    scores = scores[
        scores["points"].notna()
        & scores["opponent_team_id"].notna()
        & scores["is_playoff"].eq(False)
        & scores["is_consolation"].eq(False)
    ].copy()
    key = ["league_id", "season", "scoring_period", "source_team_id"]
    if scores.duplicated(key).any():
        raise ValueError("Team scores are not unique by season, scoring period, and team.")
    weekly_columns = [
        "league_id",
        "season",
        "scoring_period",
        "source_team_id",
        "points",
        "comparison_count",
        "all_play_wins",
        "all_play_ties",
        "expected_win_share",
        "source_file",
        "source_row_key",
        "formula_version",
    ]
    weekly_rows: list[dict[str, object]] = []
    for period_key, group in scores.groupby(key[:3], sort=True):
        if len(group) < 2:
            continue
        for row in group.itertuples(index=False):
            opponents = group[group["source_team_id"] != row.source_team_id]
            wins = int((opponents["points"] < row.points).sum())
            ties = int((opponents["points"] == row.points).sum())
            possible = len(opponents)
            weekly_rows.append(
                {
                    "league_id": int(period_key[0]),
                    "season": int(period_key[1]),
                    "scoring_period": int(period_key[2]),
                    "source_team_id": int(row.source_team_id),
                    "points": float(row.points),
                    "comparison_count": possible,
                    "all_play_wins": wins,
                    "all_play_ties": ties,
                    "expected_win_share": (wins + 0.5 * ties) / possible,
                    "source_file": str(row.source_file),
                    "source_row_key": str(row.source_row_key),
                    "formula_version": FORMULA_VERSION,
                }
            )
    weekly = pd.DataFrame(weekly_rows, columns=weekly_columns)
    season_columns = [
        "league_id",
        "season",
        "source_team_id",
        "weeks_compared",
        "expected_wins",
        "actual_wins",
        "luck_differential",
        "formula_version",
    ]
    if weekly.empty:
        return weekly, pd.DataFrame(columns=season_columns)
    actual = (
        scores.assign(actual_win=scores["result"].eq("W").astype("int64"))
        .groupby(["league_id", "season", "source_team_id"], as_index=False)
        .agg(actual_wins=("actual_win", "sum"))
    )
    season = (
        weekly.groupby(["league_id", "season", "source_team_id"], as_index=False)
        .agg(
            weeks_compared=("scoring_period", "nunique"),
            expected_wins=("expected_win_share", "sum"),
        )
        .merge(actual, on=["league_id", "season", "source_team_id"], how="left")
    )
    season["luck_differential"] = season["actual_wins"] - season["expected_wins"]
    season["formula_version"] = FORMULA_VERSION
    return weekly, season[season_columns]


def calculate_season_finishes(
    season_teams: pd.DataFrame, seasons: pd.DataFrame, facts: pd.DataFrame
) -> pd.DataFrame:
    """Retain official final placements and source-backed playoff participation."""
    teams = season_teams.copy()
    teams["official_finish"] = teams["final_rank"].fillna(teams["calculated_final_rank"])
    state = seasons[["league_id", "season", "is_active", "playoff_team_count"]]
    teams = teams.merge(state, on=["league_id", "season"], how="left", validate="many_to_one")
    entrants = set(
        map(
            tuple,
            facts.loc[
                facts["segment"].eq("championship_playoff"),
                ["league_id", "season", "source_team_id"],
            ]
            .drop_duplicates()
            .itertuples(index=False, name=None),
        )
    )
    teams["playoff_appearance"] = [
        (league, season, team) in entrants
        for league, season, team in teams[["league_id", "season", "source_team_id"]].itertuples(
            index=False, name=None
        )
    ]
    complete = teams["is_active"].eq(False) & teams["official_finish"].notna()
    teams["championship"] = complete & teams["official_finish"].eq(1)
    teams["runner_up"] = complete & teams["official_finish"].eq(2)
    teams["formula_version"] = FORMULA_VERSION
    return teams[
        [
            "league_id",
            "season",
            "source_team_id",
            "playoff_seed",
            "official_finish",
            "playoff_appearance",
            "championship",
            "runner_up",
            "is_active",
            "source_file",
            "source_row_key",
            "formula_version",
        ]
    ]


def build_manager_seasons(
    team_standings: pd.DataFrame,
    assignments: pd.DataFrame,
    *,
    expected_wins: pd.DataFrame | None = None,
    finishes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attribute team-season results using reviewed identities and explicit shared flags."""
    assigned = assignments[assignments["canonical_manager_id"].notna()].copy()
    assigned["shared_attribution"] = assigned["resolution_type"].isin(
        {"co_owner", "ownership_transfer"}
    )
    result = assigned.merge(
        team_standings,
        on=["league_id", "season", "source_team_id"],
        how="inner",
        validate="many_to_one",
    )
    optional: Iterable[tuple[pd.DataFrame | None, list[str]]] = (
        (
            expected_wins,
            ["weeks_compared", "expected_wins", "actual_wins", "luck_differential"],
        ),
        (
            finishes,
            [
                "playoff_seed",
                "official_finish",
                "playoff_appearance",
                "championship",
                "runner_up",
            ],
        ),
    )
    for frame, values in optional:
        if frame is not None:
            result = result.merge(
                frame[["league_id", "season", "source_team_id", *values]],
                on=["league_id", "season", "source_team_id"],
                how="left",
                validate="many_to_one",
            )
    result["attribution_policy_version"] = ATTRIBUTION_POLICY_VERSION
    return result.sort_values(
        ["canonical_manager_id", "season", "source_team_id"], ignore_index=True
    )


def summarize_manager_careers(manager_seasons: pd.DataFrame) -> pd.DataFrame:
    """Build careers while preserving whether any credited row was shared."""
    if manager_seasons.empty:
        return pd.DataFrame(columns=MANAGER_CAREER_COLUMNS)
    frame = manager_seasons.copy()
    for column in ("championship", "runner_up", "playoff_appearance"):
        if column not in frame:
            frame[column] = False
    if "official_finish" not in frame:
        frame["official_finish"] = pd.NA
    combined = (
        frame[frame["segment"].eq("combined")]
        if "segment" in frame and frame["segment"].eq("combined").any()
        else frame
    )
    season_rows = (
        frame[frame["segment"].eq("regular_season")]
        if "segment" in frame and frame["segment"].eq("regular_season").any()
        else combined
    )
    grouped = combined.groupby("canonical_manager_id", as_index=False).agg(
        display_name=("canonical_display_name", "first"),
        seasons_played=("season", "nunique"),
        wins=("wins", "sum"),
        losses=("losses", "sum"),
        ties=("ties", "sum"),
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
        contains_shared_attribution=("shared_attribution", "any"),
    )
    season_summary = season_rows.groupby("canonical_manager_id", as_index=False).agg(
        championships=("championship", "sum"),
        runner_up_finishes=("runner_up", "sum"),
        playoff_appearances=("playoff_appearance", "sum"),
        average_finish=("official_finish", "mean"),
        best_finish=("official_finish", "min"),
        worst_finish=("official_finish", "max"),
    )
    grouped = grouped.merge(season_summary, on="canonical_manager_id", how="left")
    for column in ("expected_wins", "luck_differential"):
        if column in season_rows:
            values = (
                season_rows.groupby("canonical_manager_id")[column]
                .sum(min_count=1)
                .rename(column)
                .reset_index()
            )
            grouped = grouped.merge(values, on="canonical_manager_id", how="left")
        else:
            grouped[column] = pd.NA
    playoff = (
        frame[frame["segment"].eq("championship_playoff")]
        if "segment" in frame
        else frame.iloc[0:0]
    )
    if playoff.empty:
        grouped[["playoff_wins", "playoff_losses", "playoff_ties"]] = 0
    else:
        playoff_summary = playoff.groupby("canonical_manager_id", as_index=False).agg(
            playoff_wins=("wins", "sum"),
            playoff_losses=("losses", "sum"),
            playoff_ties=("ties", "sum"),
        )
        grouped = grouped.merge(playoff_summary, on="canonical_manager_id", how="left")
        grouped[["playoff_wins", "playoff_losses", "playoff_ties"]] = grouped[
            ["playoff_wins", "playoff_losses", "playoff_ties"]
        ].fillna(0)
    games = grouped["wins"] + grouped["losses"] + grouped["ties"]
    grouped["win_percentage"] = (grouped["wins"] + 0.5 * grouped["ties"]) / games
    grouped["point_differential"] = grouped["points_for"] - grouped["points_against"]
    grouped["formula_version"] = FORMULA_VERSION
    grouped["attribution_policy_version"] = ATTRIBUTION_POLICY_VERSION
    return grouped[MANAGER_CAREER_COLUMNS]

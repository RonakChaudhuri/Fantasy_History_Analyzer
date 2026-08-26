"""Source-traceable league record selection with tied-holder retention."""

from __future__ import annotations

import json
from collections.abc import Callable

import pandas as pd

from fantasy_history.standings import FORMULA_VERSION, eligible_segments


def _unavailable(category: str) -> dict[str, object]:
    return {
        "category": category,
        "availability": "unavailable",
        "value": None,
        "league_id": None,
        "season": None,
        "source_team_id": None,
        "canonical_manager_id": None,
        "source_matchup_id": None,
        "source_file": None,
        "source_row_key": None,
        "source_row_keys_json": "[]",
        "formula_version": FORMULA_VERSION,
    }


def _fact_records(
    facts: pd.DataFrame,
    category: str,
    value_column: str,
    selector: Callable[[pd.Series], object],
    *,
    predicate: pd.Series | None = None,
) -> list[dict[str, object]]:
    eligible = facts[predicate].copy() if predicate is not None else facts.copy()
    eligible = eligible[eligible[value_column].notna()]
    if eligible.empty:
        return [_unavailable(category)]
    target = selector(eligible[value_column])
    selected = eligible[eligible[value_column].eq(target)]
    return [
        {
            "category": category,
            "availability": "available",
            "value": float(getattr(row, value_column)),
            "league_id": int(row.league_id),
            "season": int(row.season),
            "source_team_id": int(row.source_team_id),
            "canonical_manager_id": None,
            "source_matchup_id": int(row.source_matchup_id),
            "source_file": str(row.source_file),
            "source_row_key": str(row.source_row_key),
            "source_row_keys_json": json.dumps([str(row.source_row_key)]),
            "formula_version": FORMULA_VERSION,
        }
        for row in selected.itertuples(index=False)
    ]


def _season_records(
    facts: pd.DataFrame,
    standings: pd.DataFrame,
    category: str,
    value_column: str,
    selector: Callable[[pd.Series], object],
) -> list[dict[str, object]]:
    eligible = standings[standings[value_column].notna() & standings["completed_games"].gt(0)]
    if eligible.empty:
        return [_unavailable(category)]
    target = selector(eligible[value_column])
    selected = eligible[eligible[value_column].eq(target)]
    rows: list[dict[str, object]] = []
    for row in selected.itertuples(index=False):
        trace = facts[
            facts["league_id"].eq(row.league_id)
            & facts["season"].eq(row.season)
            & facts["source_team_id"].eq(row.source_team_id)
            & facts["segment"].isin(eligible_segments(str(row.segment)))
        ]
        keys = sorted(trace["source_row_key"].astype(str).unique().tolist())
        files = sorted(trace["source_file"].astype(str).unique().tolist())
        rows.append(
            {
                "category": category,
                "availability": "available",
                "value": float(getattr(row, value_column)),
                "league_id": int(row.league_id),
                "season": int(row.season),
                "source_team_id": int(row.source_team_id),
                "canonical_manager_id": None,
                "source_matchup_id": None,
                "source_file": files[0] if len(files) == 1 else None,
                "source_row_key": None,
                "source_row_keys_json": json.dumps(keys, separators=(",", ":")),
                "formula_version": FORMULA_VERSION,
            }
        )
    return rows


def _career_records(
    manager_careers: pd.DataFrame,
    manager_seasons: pd.DataFrame,
    attributed_facts: pd.DataFrame,
    category: str,
    value_column: str,
    *,
    season_flag: str | None = None,
) -> list[dict[str, object]]:
    eligible = manager_careers[manager_careers[value_column].notna()]
    if eligible.empty or eligible[value_column].max() <= 0:
        return [_unavailable(category)]
    target = eligible[value_column].max()
    rows: list[dict[str, object]] = []
    for career in eligible[eligible[value_column].eq(target)].itertuples(index=False):
        manager_id = str(career.canonical_manager_id)
        if season_flag is None:
            trace = attributed_facts[
                attributed_facts["manager_id"].eq(manager_id)
                & attributed_facts["segment"].eq("championship_playoff")
                & attributed_facts["result"].eq("W")
            ]
            key_column = "source_row_key"
        else:
            trace = manager_seasons[
                manager_seasons["canonical_manager_id"].eq(manager_id)
                & manager_seasons["segment"].eq("regular_season")
                & manager_seasons[season_flag].eq(True)
            ]
            key_column = "source_team_row_key"
        keys = sorted(trace[key_column].dropna().astype(str).unique().tolist())
        files = sorted(trace["source_file"].dropna().astype(str).unique().tolist())
        seasons = trace["season"].dropna().astype(int)
        matchup_ids = (
            trace["source_matchup_id"].dropna().astype(int)
            if "source_matchup_id" in trace
            else pd.Series(dtype="int64")
        )
        rows.append(
            {
                "category": category,
                "availability": "available" if keys else "unavailable",
                "value": float(target) if keys else None,
                "league_id": None,
                "season": int(seasons.max()) if not seasons.empty else None,
                "source_team_id": None,
                "canonical_manager_id": manager_id,
                "source_matchup_id": (int(matchup_ids.max()) if not matchup_ids.empty else None),
                "source_file": files[0] if len(files) == 1 else None,
                "source_row_key": keys[0] if len(keys) == 1 else None,
                "source_row_keys_json": json.dumps(keys, separators=(",", ":")),
                "formula_version": FORMULA_VERSION,
            }
        )
    return rows


def build_record_holders(
    facts: pd.DataFrame,
    *,
    team_standings: pd.DataFrame | None = None,
    streaks: pd.DataFrame | None = None,
    manager_careers: pd.DataFrame | None = None,
    manager_seasons: pd.DataFrame | None = None,
    attributed_facts: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Select initial record categories and retain every tied source holder."""
    records: list[dict[str, object]] = []
    records.extend(_fact_records(facts, "highest_weekly_score", "points_for", pd.Series.max))
    records.extend(_fact_records(facts, "lowest_weekly_score", "points_for", pd.Series.min))
    records.extend(
        _fact_records(
            facts,
            "largest_win",
            "margin",
            pd.Series.max,
            predicate=facts["result"].eq("W"),
        )
    )
    closest = facts.assign(absolute_margin=facts["margin"].abs())
    records.extend(_fact_records(closest, "closest_result", "absolute_margin", pd.Series.min))
    records.extend(
        _fact_records(
            facts,
            "most_points_in_loss",
            "points_for",
            pd.Series.max,
            predicate=facts["result"].eq("L"),
        )
    )
    records.extend(
        _fact_records(
            facts,
            "fewest_points_in_win",
            "points_for",
            pd.Series.min,
            predicate=facts["result"].eq("W"),
        )
    )
    records.extend(
        _fact_records(
            facts,
            "highest_combined_matchup_score",
            "combined_points",
            pd.Series.max,
        )
    )
    if team_standings is not None:
        records.extend(
            _season_records(
                facts,
                team_standings,
                "best_season_record",
                "win_percentage",
                pd.Series.max,
            )
        )
        records.extend(
            _season_records(
                facts,
                team_standings,
                "worst_season_record",
                "win_percentage",
                pd.Series.min,
            )
        )
        records.extend(
            _season_records(
                facts,
                team_standings,
                "highest_season_points",
                "points_for",
                pd.Series.max,
            )
        )
        records.extend(
            _season_records(
                facts,
                team_standings,
                "lowest_season_points",
                "points_for",
                pd.Series.min,
            )
        )
    if streaks is not None:
        for result, label in (
            ("W", "longest_win_streak"),
            ("L", "longest_loss_streak"),
            ("T", "longest_tie_streak"),
        ):
            eligible = streaks[streaks["result"].eq(result)]
            if eligible.empty:
                records.append(_unavailable(label))
                continue
            target = eligible["streak_length"].max()
            for row in eligible[eligible["streak_length"].eq(target)].itertuples(index=False):
                records.append(
                    {
                        "category": label,
                        "availability": "available",
                        "value": float(row.streak_length),
                        "league_id": None,
                        "season": int(row.end_season),
                        "source_team_id": int(row.source_team_id),
                        "canonical_manager_id": None,
                        "source_matchup_id": int(row.end_matchup_id),
                        "source_file": None,
                        "source_row_key": str(row.end_source_row_key),
                        "source_row_keys_json": json.dumps(
                            [str(row.start_source_row_key), str(row.end_source_row_key)],
                            separators=(",", ":"),
                        ),
                        "formula_version": FORMULA_VERSION,
                    }
                )
    if manager_careers is not None and manager_seasons is not None and attributed_facts is not None:
        for category, value_column, season_flag in (
            ("most_championships", "championships", "championship"),
            ("most_runner_up_finishes", "runner_up_finishes", "runner_up"),
            ("most_playoff_appearances", "playoff_appearances", "playoff_appearance"),
            ("most_playoff_wins", "playoff_wins", None),
        ):
            records.extend(
                _career_records(
                    manager_careers,
                    manager_seasons,
                    attributed_facts,
                    category,
                    value_column,
                    season_flag=season_flag,
                )
            )
    return pd.DataFrame(records).sort_values(
        ["category", "season", "source_team_id", "canonical_manager_id"],
        na_position="last",
        ignore_index=True,
    )

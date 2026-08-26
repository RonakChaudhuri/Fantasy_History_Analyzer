"""Pure head-to-head, margin, and streak analytics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fantasy_history.standings import (
    ATTRIBUTION_POLICY_VERSION,
    FORMULA_VERSION,
    eligible_segments,
)


def attribute_matchup_facts(facts: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    """Attach both reviewed manager perspectives while retaining shared attribution."""
    own = assignments[
        [
            "league_id",
            "season",
            "source_team_id",
            "canonical_manager_id",
            "canonical_display_name",
            "resolution_type",
        ]
    ].rename(
        columns={
            "canonical_manager_id": "manager_id",
            "canonical_display_name": "manager_name",
            "resolution_type": "manager_resolution_type",
        }
    )
    opponent = own.rename(
        columns={
            "source_team_id": "opponent_team_id",
            "manager_id": "opponent_manager_id",
            "manager_name": "opponent_manager_name",
            "manager_resolution_type": "opponent_resolution_type",
        }
    )
    result = facts.merge(
        own,
        on=["league_id", "season", "source_team_id"],
        how="left",
        validate="many_to_many",
    ).merge(
        opponent,
        on=["league_id", "season", "opponent_team_id"],
        how="left",
        validate="many_to_many",
    )
    result["shared_attribution"] = (
        result[["manager_resolution_type", "opponent_resolution_type"]]
        .isin({"co_owner", "ownership_transfer"})
        .any(axis=1)
    )
    result["attribution_policy_version"] = ATTRIBUTION_POLICY_VERSION
    return result


def summarize_head_to_head(
    facts: pd.DataFrame,
    *,
    segment: str = "combined",
    entity_column: str = "source_team_id",
    opponent_column: str = "opponent_team_id",
) -> pd.DataFrame:
    """Build directed pairwise totals that reconcile from either perspective."""
    selected = facts[facts["segment"].isin(eligible_segments(segment))].copy()
    selected = selected[
        selected[entity_column].notna()
        & selected[opponent_column].notna()
        & selected[entity_column].ne(selected[opponent_column])
    ]
    columns = [
        entity_column,
        opponent_column,
        "segment",
        "meetings",
        "wins",
        "losses",
        "ties",
        "points_for",
        "points_against",
        "point_differential",
        "average_margin",
        "biggest_win_margin",
        "closest_margin",
        "highest_combined_points",
        "contains_shared_attribution",
        "formula_version",
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected["wins"] = selected["result"].eq("W").astype("int64")
    selected["losses"] = selected["result"].eq("L").astype("int64")
    selected["ties"] = selected["result"].eq("T").astype("int64")
    selected["absolute_margin"] = selected["margin"].abs()
    selected["winning_margin"] = selected["margin"].where(selected["result"].eq("W"))
    if "shared_attribution" not in selected:
        selected["shared_attribution"] = False
    grouped = selected.groupby([entity_column, opponent_column], as_index=False).agg(
        meetings=("result", "size"),
        wins=("wins", "sum"),
        losses=("losses", "sum"),
        ties=("ties", "sum"),
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
        average_margin=("margin", "mean"),
        biggest_win_margin=("winning_margin", "max"),
        closest_margin=("absolute_margin", "min"),
        highest_combined_points=("combined_points", "max"),
        contains_shared_attribution=("shared_attribution", "any"),
    )
    grouped["segment"] = segment
    grouped["point_differential"] = grouped["points_for"] - grouped["points_against"]
    grouped["formula_version"] = FORMULA_VERSION
    return grouped[columns].sort_values([entity_column, opponent_column], ignore_index=True)


def calculate_streaks(
    facts: pd.DataFrame,
    *,
    segment: str = "combined",
    entity_column: str = "source_team_id",
    coverage_break_column: str | None = None,
) -> pd.DataFrame:
    """Return each entity's longest W/L/T streak with exact boundary rows."""
    columns = [
        entity_column,
        "segment",
        "result",
        "streak_length",
        "start_season",
        "start_matchup_id",
        "start_source_row_key",
        "end_season",
        "end_matchup_id",
        "end_source_row_key",
        "formula_version",
    ]
    selected = facts[facts["segment"].isin(eligible_segments(segment))].copy()
    if selected.empty:
        return pd.DataFrame(columns=columns)
    order = [entity_column, "season", "matchup_period", "source_matchup_id"]
    selected = selected.sort_values(order, na_position="last")
    rows: list[dict[str, object]] = []
    for entity, group in selected.groupby(entity_column, sort=True):
        current_result: str | None = None
        current: list[Any] = []
        runs: list[tuple[str, list[Any]]] = []
        for row in group.itertuples(index=False):
            breaks = bool(getattr(row, coverage_break_column)) if coverage_break_column else False
            if breaks or row.result != current_result:
                if current_result is not None:
                    runs.append((current_result, current))
                current_result = str(row.result)
                current = [row]
            else:
                current.append(row)
        if current_result is not None:
            runs.append((current_result, current))
        for result in ("W", "L", "T"):
            candidates = [run for run in runs if run[0] == result]
            if not candidates:
                continue
            _, longest = max(candidates, key=lambda run: len(run[1]))
            start, end = longest[0], longest[-1]
            rows.append(
                {
                    entity_column: entity,
                    "segment": segment,
                    "result": result,
                    "streak_length": len(longest),
                    "start_season": int(start.season),
                    "start_matchup_id": int(start.source_matchup_id),
                    "start_source_row_key": str(start.source_row_key),
                    "end_season": int(end.season),
                    "end_matchup_id": int(end.source_matchup_id),
                    "end_source_row_key": str(end.source_row_key),
                    "formula_version": FORMULA_VERSION,
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(
        [entity_column, "result"], ignore_index=True
    )

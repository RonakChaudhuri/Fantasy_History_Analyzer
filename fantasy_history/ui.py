"""Reusable presentation joins and Streamlit readiness boundary for Phase 5."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from fantasy_history.data_access import (
    DataReadiness,
    inspect_data_readiness,
    load_analytics_table,
    load_identity_table,
    load_processed_table,
)

SEGMENT_LABELS = {
    "combined": "Combined",
    "regular_season": "Regular season",
    "championship_playoff": "Championship playoffs",
    "consolation": "Consolation",
}

RECORD_LABELS = {
    "highest_weekly_score": "Highest weekly score",
    "lowest_weekly_score": "Lowest weekly score",
    "largest_win": "Largest win",
    "closest_result": "Closest result",
    "most_points_in_loss": "Most points in a loss",
    "fewest_points_in_win": "Fewest points in a win",
    "highest_combined_matchup_score": "Highest combined matchup score",
    "best_season_record": "Best season record",
    "worst_season_record": "Worst season record",
    "highest_season_points": "Highest season points",
    "lowest_season_points": "Lowest season points",
    "longest_win_streak": "Longest win streak",
    "longest_loss_streak": "Longest loss streak",
    "longest_tie_streak": "Longest tie streak",
    "most_championships": "Most championships",
    "most_runner_up_finishes": "Most runner-up finishes",
    "most_playoff_wins": "Most playoff wins",
    "most_playoff_appearances": "Most playoff appearances",
}


@st.cache_data(show_spinner=False)
def load_ui_bundle(cache_key: str) -> dict[str, pd.DataFrame]:
    """Load UI inputs under a manifest-derived cache key."""
    del cache_key
    return {
        "seasons": load_processed_table("seasons"),
        "season_teams": load_processed_table("season_teams"),
        "canonical_managers": load_identity_table("canonical_managers"),
        "assignments": load_identity_table("manager_team_assignments"),
        "facts": load_analytics_table("matchup_facts"),
        "team_standings": load_analytics_table("team_standings"),
        "season_finishes": load_analytics_table("season_finishes"),
        "manager_seasons": load_analytics_table("manager_seasons"),
        "manager_careers": load_analytics_table("manager_careers"),
        "head_to_head": load_analytics_table("head_to_head"),
        "streaks": load_analytics_table("streaks"),
        "records": load_analytics_table("record_holders"),
    }


def require_ready_data() -> tuple[DataReadiness, dict[str, pd.DataFrame]] | None:
    """Render one shared readiness boundary and stop cleanly when unavailable."""
    readiness = inspect_data_readiness()
    if not readiness.ready:
        st.error(readiness.message, icon="🧱")
        st.code(
            "python scripts/validate_identities.py --require-complete\n"
            "python scripts/rebuild_analytics.py",
            language="bash",
        )
        st.caption("No ESPN request or automatic rebuild is performed while this page renders.")
        return None
    for warning in readiness.warnings:
        st.warning(warning, icon="⚠️")
    if readiness.cache_key is None:
        raise RuntimeError("Ready data lacks a cache key.")
    return readiness, load_ui_bundle(readiness.cache_key)


def render_formula_help(readiness: DataReadiness) -> None:
    """Explain calculations and unavailable/shared states consistently."""
    with st.expander("How these numbers work"):
        st.markdown(
            "- Win percentage: `(wins + 0.5 * ties) / completed games`.\n"
            "- Expected wins compare each weekly score with every other active team; "
            "ties get half credit.\n"
            "- Luck: actual regular-season wins minus expected wins.\n"
            "- Combined records include regular season and championship playoffs, "
            "not consolation.\n"
            "- Confirmed co-owned or transferred teams give shared credit to each named manager. "
            "Shared rows must not be summed as league totals.\n"
            "- Missing and incomplete values stay unavailable; they are never converted to zero."
        )
        st.caption(
            f"Formula {readiness.formula_version} · attribution "
            f"{readiness.attribution_policy_version}"
        )


def manager_lookup(bundle: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Map canonical manager IDs to display names."""
    managers = bundle["canonical_managers"]
    return dict(
        zip(
            managers["canonical_manager_id"].astype(str),
            managers["display_name"].astype(str),
            strict=True,
        )
    )


def standings_for_segment(manager_seasons: pd.DataFrame, segment: str) -> pd.DataFrame:
    """Aggregate manager-season rows for the requested competition segment."""
    selected = manager_seasons[manager_seasons["segment"].eq(segment)].copy()
    if selected.empty:
        return selected
    selected["shared_attribution"] = selected["shared_attribution"].fillna(False)
    grouped = selected.groupby(
        ["canonical_manager_id", "canonical_display_name"], as_index=False
    ).agg(
        seasons_played=("season", "nunique"),
        wins=("wins", "sum"),
        losses=("losses", "sum"),
        ties=("ties", "sum"),
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
        championships=("championship", "sum"),
        runner_up_finishes=("runner_up", "sum"),
        playoff_appearances=("playoff_appearance", "sum"),
        playoff_wins=(
            "wins",
            lambda values: values.sum() if segment == "championship_playoff" else 0,
        ),
        average_finish=("official_finish", "mean"),
        best_finish=("official_finish", "min"),
        worst_finish=("official_finish", "max"),
        expected_wins=("expected_wins", "sum"),
        luck_differential=("luck_differential", "sum"),
        shared_credit=("shared_attribution", "any"),
    )
    games = grouped["wins"] + grouped["losses"] + grouped["ties"]
    grouped["win_percentage"] = (grouped["wins"] + 0.5 * grouped["ties"]) / games.where(games.gt(0))
    grouped["point_differential"] = grouped["points_for"] - grouped["points_against"]
    unavailable_regular_metrics = segment != "regular_season"
    if unavailable_regular_metrics:
        for column in (
            "championships",
            "runner_up_finishes",
            "playoff_appearances",
            "average_finish",
            "best_finish",
            "worst_finish",
            "expected_wins",
            "luck_differential",
        ):
            grouped[column] = pd.NA
    if segment != "championship_playoff":
        grouped["playoff_wins"] = pd.NA
    return grouped


def selected_query_value(key: str, valid: list[str], default: str) -> str:
    """Return a safe scalar query selection."""
    raw: Any = st.query_params.get(key, default)
    value = raw[0] if isinstance(raw, list) and raw else raw
    return str(value) if str(value) in valid else default


def aliases_for(manager_id: str, managers: pd.DataFrame) -> list[str]:
    """Decode reviewed team aliases for one canonical manager."""
    row = managers[managers["canonical_manager_id"].astype(str).eq(manager_id)]
    if row.empty:
        return []
    try:
        values = json.loads(str(row.iloc[0]["aliases_json"]))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(value) for value in values]


def record_holder_names(records: pd.DataFrame, bundle: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Resolve record source keys to safe manager/team display labels."""
    result = records.copy()
    names = manager_lookup(bundle)
    result["holder"] = result["canonical_manager_id"].astype("string").map(names)
    assignments = bundle["assignments"][
        ["league_id", "season", "source_team_id", "canonical_display_name"]
    ].drop_duplicates()
    result = result.merge(
        assignments,
        on=["league_id", "season", "source_team_id"],
        how="left",
    )
    result["holder"] = result["holder"].fillna(result["canonical_display_name"])
    result["category_label"] = result["category"].map(RECORD_LABELS).fillna(result["category"])
    return result

"""Reusable presentation joins and Streamlit readiness boundary for Phase 5."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd
import streamlit as st

from fantasy_history.data_access import (
    DataReadiness,
    inspect_data_readiness,
    load_analytics_table,
    load_draft_analytics_manifest,
    load_draft_analytics_table,
    load_identity_table,
    load_processed_table,
    phase6_source_cache_key,
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


def apply_app_style() -> None:
    """Apply one restrained visual system across every Streamlit page."""
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 1380px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 1rem 1.1rem;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.045);
        }
        [data-testid="stMetricLabel"] { color: #64748b; }
        [data-testid="stMetricValue"] { color: #0f172a; }
        div[data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            overflow: hidden;
        }
        div[data-testid="stTabs"] button { font-weight: 650; }
        div[data-testid="stExpander"] {
            border-color: #e2e8f0;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.7);
        }
        h1 { letter-spacing: -0.035em; }
        h2, h3 { letter-spacing: -0.02em; }
        .stCaption { color: #64748b; }
        [data-testid="stSidebar"] { border-right: 1px solid #e2e8f0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


@st.cache_data(show_spinner=False)
def load_phase6_ui_bundle(cache_key: str) -> dict[str, pd.DataFrame]:
    """Load source-supported draft and roster inputs under their own checksum."""
    del cache_key
    return {
        "drafts": load_processed_table("drafts"),
        "draft_picks": load_processed_table("draft_picks"),
        "players": load_processed_table("players"),
        "roster_snapshots": load_processed_table("roster_snapshots"),
        "roster_players": load_processed_table("roster_players"),
        "player_scores": load_processed_table("player_scores"),
    }


def require_phase6_data() -> dict[str, pd.DataFrame] | None:
    """Render a safe unavailable state when draft/roster inputs are absent."""
    cache_key = phase6_source_cache_key()
    if cache_key is None:
        st.info("Draft and roster history is unavailable. Run the offline processed-data rebuild.")
        st.caption("No ESPN request is made while this page renders.")
        return None
    return load_phase6_ui_bundle(cache_key)


@st.cache_data(show_spinner=False)
def load_draft_analytics_ui_bundle(cache_key: str) -> dict[str, pd.DataFrame]:
    """Load promoted draft analytics under their manifest checksum."""
    del cache_key
    return {
        "replacement_baselines": load_draft_analytics_table("replacement_baselines"),
        "draft_pick_values": load_draft_analytics_table("draft_pick_values"),
        "draft_position_tendencies": load_draft_analytics_table("draft_position_tendencies"),
        "repeated_players": load_draft_analytics_table("repeated_players"),
        "draft_report_cards": load_draft_analytics_table("draft_report_cards"),
    }


def require_draft_analytics_data() -> dict[str, pd.DataFrame] | None:
    """Require current draft analytics without rebuilding during page rendering."""
    from fantasy_history.draft_analytics import draft_analytics_bundle_is_current

    if not draft_analytics_bundle_is_current():
        st.info(
            "Draft-value analytics are unavailable or stale. Run "
            "`python scripts/rebuild_draft_analytics.py`."
        )
        return None
    manifest = load_draft_analytics_manifest()
    cache_key = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return load_draft_analytics_ui_bundle(cache_key)


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

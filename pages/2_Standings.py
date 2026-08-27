"""All-time manager standings."""

from __future__ import annotations

import streamlit as st

from fantasy_history.ui import (
    SEGMENT_LABELS,
    apply_app_style,
    render_formula_help,
    require_ready_data,
    standings_for_segment,
)

st.set_page_config(page_title="Standings · Fantasy History", page_icon="📊", layout="wide")
apply_app_style()
st.title("All-time standings")
st.caption("A quick career leaderboard, with the full stat sheet one tab away.")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded

segments: list[str] = list(SEGMENT_LABELS)
filters = st.columns((2, 3))
segment = filters[0].selectbox(
    "Competition segment",
    segments,
    format_func=lambda value: SEGMENT_LABELS[value],
    help="Combined excludes consolation games.",
)
search = filters[1].text_input("Find a manager", placeholder="Type a name")

if segment == "combined":
    table = bundle["manager_careers"].rename(
        columns={
            "canonical_manager_id": "manager_id",
            "display_name": "manager",
            "contains_shared_attribution": "shared_credit",
        }
    )
else:
    table = standings_for_segment(bundle["manager_seasons"], segment).rename(
        columns={
            "canonical_manager_id": "manager_id",
            "canonical_display_name": "manager",
        }
    )
if search:
    table = table[table["manager"].str.contains(search, case=False, na=False)]

columns = [
    "manager",
    "seasons_played",
    "wins",
    "losses",
    "ties",
    "win_percentage",
    "points_for",
    "points_against",
    "point_differential",
    "championships",
    "runner_up_finishes",
    "playoff_appearances",
    "playoff_wins",
    "average_finish",
    "best_finish",
    "worst_finish",
    "expected_wins",
    "luck_differential",
    "shared_credit",
]
visible = table[[column for column in columns if column in table]].sort_values(
    ["win_percentage", "wins"], ascending=False, na_position="last"
)
if visible.empty:
    st.info("No managers match these filters.")
else:
    leader = visible.iloc[0]
    leader_metrics = st.columns(3)
    leader_metrics[0].metric("Leaderboard", str(leader["manager"]))
    leader_metrics[1].metric("Best win rate", f"{float(leader['win_percentage']):.3f}")
    leader_metrics[2].metric("Career wins", int(leader["wins"]))

    summary_tab, full_tab = st.tabs(["Leaderboard", "Full stat sheet"])
    with summary_tab:
        summary = visible.copy()
        summary.insert(0, "rank", range(1, len(summary) + 1))
        summary["record"] = (
            summary["wins"].astype("Int64").astype("string")
            + "-"
            + summary["losses"].astype("Int64").astype("string")
            + "-"
            + summary["ties"].astype("Int64").astype("string")
        )
        compact_columns = [
            "rank",
            "manager",
            "record",
            "win_percentage",
            "championships",
            "seasons_played",
            "points_for",
            "luck_differential",
        ]
        st.dataframe(
            summary[[column for column in compact_columns if column in summary]],
            width="stretch",
            hide_index=True,
            column_config={
                "rank": "#",
                "manager": "Manager",
                "record": "Record",
                "win_percentage": st.column_config.NumberColumn("Win %", format="%.3f"),
                "championships": "Titles",
                "seasons_played": "Seasons",
                "points_for": st.column_config.NumberColumn("Points", format="%.1f"),
                "luck_differential": st.column_config.NumberColumn("Luck", format="%+.1f"),
            },
        )
    with full_tab:
        st.caption("Every available career measure. Scroll horizontally for the full history.")
        st.dataframe(
            visible,
            width="stretch",
            hide_index=True,
            column_config={
                "manager": "Manager",
                "win_percentage": st.column_config.NumberColumn("Win %", format="%.3f"),
                "points_for": st.column_config.NumberColumn("Points for", format="%.2f"),
                "points_against": st.column_config.NumberColumn("Points against", format="%.2f"),
                "point_differential": st.column_config.NumberColumn("Point diff.", format="%+.2f"),
                "luck_differential": st.column_config.NumberColumn("Luck", format="%+.2f"),
                "shared_credit": st.column_config.CheckboxColumn("Shared credit"),
            },
        )
        st.download_button(
            "Download these standings",
            visible.to_csv(index=False, na_rep="").encode("utf-8"),
            file_name=f"fantasy-standings-{segment}.csv",
            mime="text/csv",
        )
        st.caption("Shared-credit careers are marked and must not be summed as league totals.")
render_formula_help(readiness)

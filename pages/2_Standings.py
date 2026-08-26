"""All-time manager standings."""

from __future__ import annotations

import streamlit as st

from fantasy_history.ui import (
    SEGMENT_LABELS,
    render_formula_help,
    require_ready_data,
    standings_for_segment,
)

st.set_page_config(page_title="Standings · Fantasy History", page_icon="📊", layout="wide")
st.title("All-time standings")
st.caption("Canonical careers across renamed teams and reviewed ownership changes.")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded

segments: list[str] = list(SEGMENT_LABELS)
segment = st.selectbox(
    "Competition segment",
    segments,
    format_func=lambda value: SEGMENT_LABELS[value],
    help="Combined excludes consolation games.",
)
search = st.text_input("Filter managers", placeholder="Start typing a manager name")

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
    "Download filtered standings (CSV)",
    visible.to_csv(index=False, na_rep="").encode("utf-8"),
    file_name=f"fantasy-standings-{segment}.csv",
    mime="text/csv",
)
st.caption(
    "Shared-credit careers are visibly marked and must not be summed to calculate league totals."
)
render_formula_help(readiness)

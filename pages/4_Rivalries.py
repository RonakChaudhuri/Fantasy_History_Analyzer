"""Two-manager rivalry comparison and league matrix."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.rivalries import attribute_matchup_facts, summarize_head_to_head
from fantasy_history.ui import (
    SEGMENT_LABELS,
    apply_app_style,
    manager_lookup,
    render_formula_help,
    require_ready_data,
    selected_query_value,
)

st.set_page_config(page_title="Rivalries · Fantasy History", page_icon="⚔️", layout="wide")
apply_app_style()
st.title("Rivalries")
st.caption(
    "Pick two managers for the story; detailed meetings and the league matrix stay tucked away."
)

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded
names = manager_lookup(bundle)
manager_ids = sorted(names, key=lambda value: names[value].casefold())

segments: list[str] = list(SEGMENT_LABELS)
segment = st.selectbox(
    "Competition segment", segments, format_func=lambda value: SEGMENT_LABELS[value]
)
left_default = selected_query_value("manager_a", manager_ids, manager_ids[0])
right_candidates = [value for value in manager_ids if value != left_default]
right_default = selected_query_value("manager_b", right_candidates, right_candidates[0])
selectors = st.columns(2)
manager_a = selectors[0].selectbox(
    "First manager",
    manager_ids,
    index=manager_ids.index(left_default),
    format_func=lambda value: names[value],
)
manager_b_options = [value for value in manager_ids if value != manager_a]
if right_default not in manager_b_options:
    right_default = manager_b_options[0]
manager_b = selectors[1].selectbox(
    "Second manager",
    manager_b_options,
    index=manager_b_options.index(right_default),
    format_func=lambda value: names[value],
)
st.query_params["manager_a"] = manager_a
st.query_params["manager_b"] = manager_b

attributed = attribute_matchup_facts(bundle["facts"], bundle["assignments"])
summary = summarize_head_to_head(
    attributed,
    segment=segment,
    entity_column="manager_id",
    opponent_column="opponent_manager_id",
)
pair = summary[
    summary["manager_id"].astype(str).eq(manager_a)
    & summary["opponent_manager_id"].astype(str).eq(manager_b)
]
st.subheader(f"{names[manager_a]} vs. {names[manager_b]}")
if pair.empty:
    st.info(f"No completed {SEGMENT_LABELS[segment].lower()} meetings are available.")
else:
    row = pair.iloc[0]
    metrics = st.columns(4)
    metrics[0].metric("Record", f"{int(row['wins'])}-{int(row['losses'])}-{int(row['ties'])}")
    metrics[1].metric("Meetings", int(row["meetings"]))
    metrics[2].metric("Average margin", f"{row['average_margin']:+.2f}")
    metrics[3].metric("Closest game", f"{row['closest_margin']:.2f} pts")
    st.caption(
        f"Biggest win: {row['biggest_win_margin']:.2f} · highest combined score: "
        f"{row['highest_combined_points']:.2f} · shared attribution: "
        f"{'yes' if row['contains_shared_attribution'] else 'no'}"
    )

history = attributed[
    attributed["manager_id"].astype(str).eq(manager_a)
    & attributed["opponent_manager_id"].astype(str).eq(manager_b)
]
eligible_segments = (
    ["regular_season", "championship_playoff"] if segment == "combined" else [segment]
)
history = history[history["segment"].isin(eligible_segments)].sort_values(
    ["season", "matchup_period", "source_matchup_id"]
)
st.subheader("Chronological meetings")
if history.empty:
    st.caption("No matchup history is available for this selection.")
else:
    history = history.copy()
    history["rivalry_lead"] = history["result"].map({"W": 1, "L": -1, "T": 0}).cumsum()
    runs = history["result"].ne(history["result"].shift()).cumsum().rename("run_id")
    longest = history.groupby([runs, "result"]).size().reset_index(name="length")
    longest_labels = {
        result: int(group["length"].max()) for result, group in longest.groupby("result")
    }
    current_result = str(history.iloc[-1]["result"])
    current_length = int((runs == runs.iloc[-1]).sum())
    st.caption(
        f"Current streak: {current_length} {current_result} · longest: "
        f"{longest_labels.get('W', 0)} W / {longest_labels.get('L', 0)} L / "
        f"{longest_labels.get('T', 0)} T"
    )
    chart = px.line(
        history,
        x=history.index,
        y="rivalry_lead",
        markers=True,
        title=f"Rivalry lead over time ({names[manager_a]} perspective)",
        labels={"index": "Meeting", "rivalry_lead": "Cumulative lead"},
        hover_data=["season", "matchup_period", "points_for", "points_against", "result"],
    )
    st.plotly_chart(chart, width="stretch")
    with st.expander(f"View all {len(history)} meetings"):
        st.dataframe(
            history[
                [
                    "season",
                    "matchup_period",
                    "segment",
                    "points_for",
                    "points_against",
                    "result",
                    "margin",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "matchup_period": "Week",
                "segment": "Stage",
                "points_for": st.column_config.NumberColumn(names[manager_a], format="%.1f"),
                "points_against": st.column_config.NumberColumn(names[manager_b], format="%.1f"),
                "result": "Result",
                "margin": st.column_config.NumberColumn("Margin", format="%+.1f"),
            },
        )

matrix = summary.pivot(index="manager_id", columns="opponent_manager_id", values="wins")
matrix = matrix.rename(index=names, columns=names)
with st.expander("League-wide head-to-head matrix"):
    st.caption("Each cell is the row manager's wins against the column manager.")
    st.dataframe(matrix, width="stretch")
render_formula_help(readiness)

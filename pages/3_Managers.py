"""Canonical manager profile journey."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.formatting import format_points, format_record, format_signed
from fantasy_history.ui import (
    aliases_for,
    manager_lookup,
    record_holder_names,
    render_formula_help,
    require_ready_data,
    selected_query_value,
)

st.set_page_config(page_title="Managers · Fantasy History", page_icon="👤", layout="wide")
st.title("Manager profiles")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded
names = manager_lookup(bundle)
manager_ids = sorted(names, key=lambda value: names[value].casefold())
default = selected_query_value("manager", manager_ids, manager_ids[0])
selector_key = "manager_profile_selector"
query_marker_key = "manager_profile_query_value"
if selector_key not in st.session_state:
    st.session_state[query_marker_key] = default
    selector_index: int | None = manager_ids.index(default)
elif st.session_state.get(query_marker_key) != default:
    # A shared URL changed externally; update the widget before it is instantiated.
    st.session_state[selector_key] = default
    st.session_state[query_marker_key] = default
    selector_index = None
else:
    selector_index = None


def sync_manager_query() -> None:
    """Commit one dropdown interaction to the shareable URL before rerendering."""
    selected = str(st.session_state[selector_key])
    st.query_params["manager"] = selected
    st.session_state[query_marker_key] = selected


manager_id = st.selectbox(
    "Manager",
    manager_ids,
    index=selector_index,
    format_func=lambda value: names[value],
    key=selector_key,
    on_change=sync_manager_query,
)
if manager_id is None:
    st.stop()

career_rows = bundle["manager_careers"][
    bundle["manager_careers"]["canonical_manager_id"].astype(str).eq(manager_id)
]
if career_rows.empty:
    st.info("Career analytics are unavailable for this manager.")
    st.stop()
career = career_rows.iloc[0]
st.subheader(str(career["display_name"]))
aliases = aliases_for(manager_id, bundle["canonical_managers"])
st.caption("Team-name history: " + (" · ".join(aliases) if aliases else "Unavailable"))

metrics = st.columns(4)
metrics[0].metric("Career record", format_record(career["wins"], career["losses"], career["ties"]))
metrics[1].metric("Career points", format_points(career["points_for"]))
metrics[2].metric("Championships", int(career["championships"]))
metrics[3].metric("Luck", format_signed(career["luck_differential"]))
if bool(career["contains_shared_attribution"]):
    st.info("This career includes confirmed shared ownership or transfer attribution.", icon="🤝")

seasons = bundle["manager_seasons"]
seasons = seasons[
    seasons["canonical_manager_id"].astype(str).eq(manager_id)
    & seasons["segment"].eq("regular_season")
].sort_values("season")
st.subheader("Season history")
season_columns = [
    "season",
    "wins",
    "losses",
    "ties",
    "points_for",
    "official_finish",
    "playoff_seed",
    "playoff_appearance",
    "championship",
    "runner_up",
    "expected_wins",
    "luck_differential",
    "shared_attribution",
]
st.dataframe(seasons[season_columns], width="stretch", hide_index=True)

if not seasons.empty:
    trend = seasons.melt(
        id_vars="season",
        value_vars=["wins", "expected_wins"],
        var_name="measure",
        value_name="value",
    )
    figure = px.line(
        trend,
        x="season",
        y="value",
        color="measure",
        markers=True,
        title="Actual and expected regular-season wins",
        labels={"value": "Wins", "season": "Season", "measure": "Measure"},
    )
    st.plotly_chart(figure, width="stretch")

st.subheader("Opponents")
head = bundle["head_to_head"][
    bundle["head_to_head"]["manager_id"].astype(str).eq(manager_id)
].copy()
head["opponent"] = head["opponent_manager_id"].astype(str).map(names)
if head.empty:
    st.info("No completed head-to-head meetings are available.")
else:
    opponent_columns = [
        "opponent",
        "meetings",
        "wins",
        "losses",
        "ties",
        "points_for",
        "points_against",
        "point_differential",
        "average_margin",
        "closest_margin",
        "contains_shared_attribution",
    ]
    st.dataframe(
        head[opponent_columns].sort_values("meetings", ascending=False),
        width="stretch",
        hide_index=True,
    )
    eligible = head[head["meetings"].gt(0)].copy()
    eligible["win_share"] = (eligible["wins"] + 0.5 * eligible["ties"]) / eligible["meetings"]
    favorite = eligible.sort_values(["win_share", "meetings"], ascending=False).iloc[0]
    nemesis = eligible.sort_values(["win_share", "meetings"], ascending=[True, False]).iloc[0]
    cols = st.columns(2)
    cols[0].metric(
        "Favorite opponent",
        str(favorite["opponent"]),
        f"{favorite['win_share']:.3f} win share",
    )
    cols[1].metric("Nemesis", str(nemesis["opponent"]), f"{nemesis['win_share']:.3f} win share")

held = record_holder_names(bundle["records"], bundle)
held = held[held["canonical_manager_id"].astype("string").eq(manager_id)]
st.subheader("Records held")
if held.empty:
    st.caption("No manager-level league records currently held.")
else:
    st.dataframe(held[["category_label", "value", "season"]], width="stretch", hide_index=True)

render_formula_help(readiness)

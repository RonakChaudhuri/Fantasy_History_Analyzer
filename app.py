"""Streamlit overview for the promoted, read-only league history."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.formatting import format_points, format_record
from fantasy_history.ui import record_holder_names, render_formula_help, require_ready_data

st.set_page_config(
    page_title="Fantasy History Analyzer",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏈 Fantasy History Analyzer")
st.caption("Every season. Every rivalry. Every receipt.")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded

seasons = bundle["seasons"].sort_values("season")
facts = bundle["facts"]
careers = bundle["manager_careers"]
manager_seasons = bundle["manager_seasons"]
league_name = str(seasons.iloc[-1]["league_name"])
active_count = int(seasons["is_active"].fillna(False).sum())
completed_seasons = int(len(seasons) - active_count)
matchup_count = facts[["season", "source_matchup_id"]].drop_duplicates().shape[0]

st.subheader(league_name)
metrics = st.columns(4)
metrics[0].metric("Seasons", len(seasons), help=f"{completed_seasons} completed")
metrics[1].metric("Completed matchups", f"{matchup_count:,}")
metrics[2].metric("Total points", format_points(float(facts["points_for"].sum())))
metrics[3].metric("Active seasons", active_count)

regular = manager_seasons[manager_seasons["segment"].eq("regular_season")]
champions = regular[regular["championship"].eq(True) & regular["official_finish"].notna()].copy()
champions = champions.sort_values("season")
latest_champion = champions.iloc[-1] if not champions.empty else None

left, right = st.columns((3, 2))
with left:
    st.subheader("Champions timeline")
    if champions.empty:
        st.info("Championship history is unavailable.")
    else:
        chart = px.bar(
            champions,
            x="season",
            y="points_for",
            color="canonical_display_name",
            labels={
                "season": "Season",
                "points_for": "Regular-season points",
                "canonical_display_name": "Champion",
            },
            title="Champions by season and regular-season scoring",
            hover_data={"wins": True, "losses": True, "ties": True},
        )
        chart.update_layout(margin=dict(l=0, r=0, t=50, b=0), legend_title_text="Champion")
        st.plotly_chart(chart, width="stretch")
with right:
    st.subheader("League leaders")
    if latest_champion is None:
        st.metric("Latest completed champion", "Unavailable")
    else:
        st.metric(
            f"{int(latest_champion['season'])} champion",
            str(latest_champion["canonical_display_name"]),
        )
    if careers.empty:
        st.metric("Championship leader", "Unavailable")
        st.metric("Best all-time record", "Unavailable")
    else:
        title_leader = careers.sort_values(
            ["championships", "win_percentage"], ascending=False
        ).iloc[0]
        eligible = careers[careers["wins"].add(careers["losses"]).add(careers["ties"]).gt(0)]
        best_record = eligible.sort_values("win_percentage", ascending=False).iloc[0]
        st.metric(
            "Championship leader",
            str(title_leader["display_name"]),
            f"{int(title_leader['championships'])} titles",
        )
        st.metric(
            "Best all-time record",
            str(best_record["display_name"]),
            format_record(best_record["wins"], best_record["losses"], best_record["ties"]),
        )

st.subheader("Records cabinet")
named_records = record_holder_names(bundle["records"], bundle)
featured = named_records[
    named_records["category"].isin(
        ["highest_weekly_score", "lowest_weekly_score", "closest_result", "largest_win"]
    )
    & named_records["availability"].eq("available")
].drop_duplicates("category")
columns = st.columns(2)
for index, row in enumerate(featured.itertuples(index=False)):
    with columns[index % 2]:
        st.metric(str(row.category_label), format_points(float(row.value)))
        st.caption(f"{row.holder or 'Unavailable'} · {int(row.season)}")

head = bundle["head_to_head"]
if not head.empty:
    spotlight = head.sort_values(["meetings", "closest_margin"], ascending=[False, True]).iloc[0]
    names = dict(zip(careers["canonical_manager_id"], careers["display_name"], strict=True))
    st.subheader("Rivalry spotlight")
    st.write(
        f"**{names.get(spotlight['manager_id'], spotlight['manager_id'])} vs. "
        f"{names.get(spotlight['opponent_manager_id'], spotlight['opponent_manager_id'])}** · "
        f"{int(spotlight['meetings'])} meetings · "
        f"{int(spotlight['wins'])}-{int(spotlight['losses'])}-{int(spotlight['ties'])}"
    )

render_formula_help(readiness)
st.caption(
    f"Status: {readiness.status} · formula {readiness.formula_version} · "
    "freshness unavailable · no ESPN request is made while this page renders"
)

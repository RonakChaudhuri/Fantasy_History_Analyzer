"""Streamlit entry point for the fixture-powered Phase 1 preview."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.data_access import champions_frame, load_demo_overview
from fantasy_history.formatting import format_points

st.set_page_config(
    page_title="Fantasy History Analyzer",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

overview = load_demo_overview()
summary = overview["summary"]

st.title("🏈 Fantasy History Analyzer")
st.caption("Every season. Every rivalry. Every receipt.")
st.info(str(overview["notice"]), icon="🧪")

st.subheader(str(overview["league_name"]))
metric_columns = st.columns(4)
metric_columns[0].metric("Seasons", summary["seasons"])
metric_columns[1].metric("Matchups", f"{summary['matchups']:,}")
metric_columns[2].metric("Total points", format_points(float(summary["total_points"])))
metric_columns[3].metric("Latest champion", summary["latest_champion"])

left, right = st.columns((3, 2))
with left:
    st.subheader("Champions timeline")
    champions = champions_frame(overview)
    figure = px.bar(
        champions,
        x="season",
        y="points",
        color="manager",
        labels={"season": "Season", "points": "Championship score", "manager": "Champion"},
        hover_data={"season": True, "manager": True, "points": ":.2f"},
    )
    figure.update_layout(legend_title_text="Champion", margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(figure, width="stretch")

with right:
    st.subheader("League leaders")
    st.metric("Championship leader", summary["championship_leader"])
    st.metric("Best all-time record", summary["best_record"])
    st.caption("Career and season analytics arrive after validated ESPN normalization.")

st.subheader("Records cabinet")
record_columns = st.columns(len(overview["records"]))
for column, record in zip(record_columns, overview["records"], strict=True):
    with column:
        st.metric(record["label"], record["value"])
        st.caption(record["detail"])

st.divider()
st.caption("Preview status · fixture data · no ESPN request is made while this page renders")

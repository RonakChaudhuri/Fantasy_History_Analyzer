"""Traceable league records cabinet."""

from __future__ import annotations

import streamlit as st

from fantasy_history.formatting import format_points
from fantasy_history.ui import RECORD_LABELS, record_holder_names, require_ready_data

st.set_page_config(page_title="Records · Fantasy History", page_icon="🏆", layout="wide")
st.title("Records cabinet")
st.caption("Every available record retains processed source identifiers.")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded
records = record_holder_names(bundle["records"], bundle)
categories = sorted(
    records["category"].astype(str).unique(),
    key=lambda value: RECORD_LABELS.get(value, value),
)
chosen = st.multiselect(
    "Categories",
    categories,
    default=categories,
    format_func=lambda value: RECORD_LABELS.get(value, value),
)
season_options = sorted(records["season"].dropna().astype(int).unique(), reverse=True)
season_filter = st.multiselect("Seasons (optional)", season_options)
filtered = records[records["category"].isin(chosen)]
if season_filter:
    filtered = filtered[filtered["season"].isin(season_filter)]

display = filtered[["category_label", "holder", "value", "season", "availability"]].rename(
    columns={"category_label": "record", "availability": "status"}
)
st.dataframe(display, width="stretch", hide_index=True)

with st.expander("Source details"):
    st.caption(
        "Identifiers below locate normalized source rows; raw ESPN payloads are never exposed."
    )
    st.dataframe(
        filtered[
            [
                "category_label",
                "holder",
                "season",
                "source_matchup_id",
                "source_team_id",
                "source_file",
                "source_row_key",
                "source_row_keys_json",
                "formula_version",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

available = filtered[filtered["availability"].eq("available")]
if not available.empty:
    st.subheader("Selected highlights")
    for row in available.head(4).itertuples(index=False):
        st.metric(str(row.category_label), format_points(float(row.value)))
        season_label = int(row.season) if row.season == row.season else "Unavailable"
        st.caption(f"{row.holder or 'Unavailable'} · {season_label}")
st.caption(f"Formula {readiness.formula_version} · tied holders are shown as separate rows.")

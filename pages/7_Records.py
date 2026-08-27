"""Traceable league records cabinet."""

from __future__ import annotations

import streamlit as st

from fantasy_history.formatting import format_points
from fantasy_history.ui import (
    RECORD_LABELS,
    apply_app_style,
    record_holder_names,
    require_ready_data,
)

st.set_page_config(page_title="Records · Fantasy History", page_icon="🏆", layout="wide")
apply_app_style()
st.title("Records cabinet")
st.caption("League landmarks first; filters and source receipts are available when you want them.")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded
records = record_holder_names(bundle["records"], bundle)
featured = records[
    records["availability"].eq("available")
    & records["category"].isin(
        ["highest_weekly_score", "largest_win", "closest_result", "most_championships"]
    )
].drop_duplicates("category")
highlight_columns = st.columns(4)
for index, row in enumerate(featured.itertuples(index=False)):
    with highlight_columns[index % 4]:
        display_value = (
            str(int(row.value))
            if row.category == "most_championships"
            else format_points(float(row.value))
        )
        st.metric(str(row.category_label), display_value)
        season_label = int(row.season) if row.season == row.season else "All time"
        st.caption(f"{row.holder or 'Unavailable'} · {season_label}")

categories = sorted(
    records["category"].astype(str).unique(),
    key=lambda value: RECORD_LABELS.get(value, value),
)
season_options = sorted(records["season"].dropna().astype(int).unique(), reverse=True)
with st.expander("Filter the records list"):
    chosen = st.multiselect(
        "Categories",
        categories,
        default=categories,
        format_func=lambda value: RECORD_LABELS.get(value, value),
    )
    season_filter = st.multiselect("Seasons (optional)", season_options)
filtered = records[records["category"].isin(chosen)]
if season_filter:
    filtered = filtered[filtered["season"].isin(season_filter)]

display = filtered[["category_label", "holder", "value", "season", "availability"]].rename(
    columns={"category_label": "record", "availability": "status"}
)
st.subheader("Record book")
st.dataframe(
    display,
    width="stretch",
    hide_index=True,
    column_config={
        "record": "Record",
        "holder": "Holder",
        "value": st.column_config.NumberColumn("Value", format="%.2f"),
        "season": "Season",
        "status": "Status",
    },
)

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

st.caption(f"Formula {readiness.formula_version} · tied holders are shown as separate rows.")

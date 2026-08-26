"""Season standings, weekly scores, and playoffs."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.ui import render_formula_help, require_ready_data, selected_query_value

st.set_page_config(page_title="Seasons · Fantasy History", page_icon="📅", layout="wide")
st.title("Seasons")

loaded = require_ready_data()
if loaded is None:
    st.stop()
readiness, bundle = loaded
seasons = bundle["seasons"].sort_values("season", ascending=False)
season_values = [str(int(value)) for value in seasons["season"]]
default = selected_query_value("season", season_values, season_values[0])
selector_key = "season_profile_selector"
query_marker_key = "season_profile_query_value"
if selector_key not in st.session_state:
    st.session_state[query_marker_key] = default
    selector_index: int | None = season_values.index(default)
elif st.session_state.get(query_marker_key) != default:
    st.session_state[selector_key] = default
    st.session_state[query_marker_key] = default
    selector_index = None
else:
    selector_index = None


def sync_season_query() -> None:
    """Commit one season interaction to the shareable URL before rerendering."""
    selected_season = str(st.session_state[selector_key])
    st.query_params["season"] = selected_season
    st.session_state[query_marker_key] = selected_season


selected = st.selectbox(
    "Season",
    season_values,
    index=selector_index,
    key=selector_key,
    on_change=sync_season_query,
)
if selected is None:
    st.stop()
season = int(selected)
season_row = seasons[seasons["season"].eq(season)].iloc[0]
if bool(season_row["is_active"]):
    st.warning(
        f"{season} is active. Standings, matchups, and finishes are partial; "
        "unavailable values remain blank.",
        icon="⚠️",
    )

teams = bundle["season_teams"][bundle["season_teams"]["season"].eq(season)][
    ["league_id", "season", "source_team_id", "team_name"]
]
regular = bundle["team_standings"]
regular = regular[regular["season"].eq(season) & regular["segment"].eq("regular_season")]
finishes = bundle["season_finishes"][bundle["season_finishes"]["season"].eq(season)]
standings = regular.merge(
    finishes,
    on=["league_id", "season", "source_team_id", "formula_version"],
    how="outer",
).merge(teams, on=["league_id", "season", "source_team_id"], how="left")
st.subheader("Standings and finish")
if standings.empty:
    st.info("Season standings are unavailable.")
else:
    display_columns = [
        "team_name",
        "playoff_seed",
        "official_finish",
        "wins",
        "losses",
        "ties",
        "win_percentage",
        "points_for",
        "points_against",
        "playoff_appearance",
        "championship",
        "runner_up",
    ]
    st.dataframe(
        standings[display_columns].sort_values(
            ["official_finish", "win_percentage"], ascending=[True, False], na_position="last"
        ),
        width="stretch",
        hide_index=True,
    )

facts = bundle["facts"][bundle["facts"]["season"].eq(season)].merge(
    teams[["source_team_id", "team_name"]], on="source_team_id", how="left"
)
st.subheader("Weekly scores")
if facts.empty:
    st.info("Completed weekly scores are unavailable for this season.")
else:
    chart = px.line(
        facts.sort_values("scoring_period"),
        x="scoring_period",
        y="points_for",
        color="team_name",
        markers=True,
        title=f"{season} completed team scores",
        labels={"scoring_period": "Scoring period", "points_for": "Points", "team_name": "Team"},
    )
    st.plotly_chart(chart, width="stretch")
    st.dataframe(
        facts[
            ["scoring_period", "team_name", "points_for", "points_against", "result", "segment"]
        ].sort_values(["scoring_period", "team_name"]),
        width="stretch",
        hide_index=True,
    )

st.subheader("Championship bracket results")
playoffs = facts[facts["segment"].eq("championship_playoff")]
if playoffs.empty:
    st.info("Championship-bracket results are unavailable or have not started.")
else:
    st.dataframe(
        playoffs[["matchup_period", "team_name", "points_for", "points_against", "result"]],
        width="stretch",
        hide_index=True,
    )
st.caption("Draft board and final-roster history arrive in Phase 6.")
render_formula_help(readiness)

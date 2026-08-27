"""Season standings, weekly scores, and playoffs."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.draft_value import attach_actual_production, select_completed_roster
from fantasy_history.ui import (
    apply_app_style,
    render_formula_help,
    require_phase6_data,
    require_ready_data,
    selected_query_value,
)

st.set_page_config(page_title="Seasons · Fantasy History", page_icon="📅", layout="wide")
apply_app_style()
st.title("Seasons")
st.caption("A season at a glance, organized into standings, scores, playoffs, and roster history.")
st.markdown(
    """
    <style>
    .st-key-season_profile_selector label p {
        font-size: 1.05rem;
        font-weight: 650;
    }
    .st-key-season_profile_selector [data-baseweb="select"] > div {
        min-height: 3.5rem;
        font-size: 1.2rem;
        font-weight: 650;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
facts = bundle["facts"][bundle["facts"]["season"].eq(season)].merge(
    teams[["source_team_id", "team_name"]], on="source_team_id", how="left"
)
playoffs = facts[facts["segment"].eq("championship_playoff")]

season_metrics = st.columns(3)
season_metrics[0].metric("Teams", int(teams["source_team_id"].nunique()))
season_metrics[1].metric(
    "Completed games", int(facts[["source_matchup_id"]].drop_duplicates().shape[0])
)
champion_rows = standings[standings["championship"].eq(True)] if not standings.empty else standings
season_metrics[2].metric(
    "Champion",
    str(champion_rows.iloc[0]["team_name"]) if not champion_rows.empty else "Unavailable",
)

standings_tab, scores_tab, players_tab, playoffs_tab, roster_tab = st.tabs(
    ["Standings", "Weekly scores", "Best players", "Playoffs", "Draft & roster"]
)
with standings_tab:
    if standings.empty:
        st.info("Season standings are unavailable.")
    else:
        ordered = standings.sort_values(
            ["official_finish", "win_percentage"], ascending=[True, False], na_position="last"
        )
        compact = [
            "team_name",
            "official_finish",
            "wins",
            "losses",
            "ties",
            "win_percentage",
            "points_for",
            "playoff_appearance",
        ]
        st.dataframe(
            ordered[compact],
            width="stretch",
            hide_index=True,
            column_config={
                "team_name": "Team",
                "official_finish": "Finish",
                "win_percentage": st.column_config.NumberColumn("Win %", format="%.3f"),
                "points_for": st.column_config.NumberColumn("Points", format="%.1f"),
                "playoff_appearance": "Playoffs",
            },
        )
        with st.expander("Full standings details"):
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
            st.dataframe(ordered[display_columns], width="stretch", hide_index=True)

with scores_tab:
    if facts.empty:
        st.info("Completed weekly scores are unavailable for this season.")
    else:
        chart = px.line(
            facts.sort_values("scoring_period"),
            x="scoring_period",
            y="points_for",
            color="team_name",
            markers=True,
            labels={
                "scoring_period": "Week",
                "points_for": "Points",
                "team_name": "Team",
            },
        )
        chart.update_layout(margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(chart, width="stretch")
        with st.expander("Weekly score table"):
            st.dataframe(
                facts[
                    [
                        "scoring_period",
                        "team_name",
                        "points_for",
                        "points_against",
                        "result",
                        "segment",
                    ]
                ].sort_values(["scoring_period", "team_name"]),
                width="stretch",
                hide_index=True,
            )

with players_tab:
    st.subheader("Best players of the year")
    phase6 = require_phase6_data()
    if phase6 is not None:
        roster = select_completed_roster(
            season,
            bundle["seasons"],
            phase6["roster_snapshots"],
            phase6["roster_players"],
            bundle["season_teams"],
            bundle["assignments"],
        )
        if not roster.available:
            st.info(roster.message)
        else:
            players = attach_actual_production(
                roster.rows, phase6["player_scores"], bundle["seasons"]
            )
            leaders = (
                players[players["production_eligibility"].eq("eligible")]
                .sort_values(
                    ["actual_fantasy_points", "player_name"],
                    ascending=[False, True],
                    kind="stable",
                )
                .head(10)
                .copy()
            )
            if leaders.empty:
                st.info("Player season totals are unavailable for this season.")
            else:
                leaders.insert(0, "rank", range(1, len(leaders) + 1))
                st.dataframe(
                    leaders[
                        [
                            "rank",
                            "player_name",
                            "position",
                            "actual_fantasy_points",
                            "team_name",
                            "manager_name",
                        ]
                    ],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "rank": "Rank",
                        "player_name": "Player",
                        "position": "Pos.",
                        "actual_fantasy_points": st.column_config.NumberColumn(
                            "Fantasy points", format="%.1f"
                        ),
                        "team_name": "Fantasy team",
                        "manager_name": "Manager",
                    },
                )
                st.caption(
                    "Ranked by ESPN's recorded season-total fantasy points. Ownership is the "
                    "validated completed-season roster snapshot, not a full transaction history."
                )

with playoffs_tab:
    if playoffs.empty:
        st.info("Championship-bracket results are unavailable or have not started.")
    else:
        st.dataframe(
            playoffs[["matchup_period", "team_name", "points_for", "points_against", "result"]],
            width="stretch",
            hide_index=True,
            column_config={
                "matchup_period": "Week",
                "team_name": "Team",
                "points_for": st.column_config.NumberColumn("Points", format="%.1f"),
                "points_against": st.column_config.NumberColumn("Opponent", format="%.1f"),
                "result": "Result",
            },
        )

with roster_tab:
    st.markdown(f"[Open the full {season} draft and roster view](Drafts?season={season})")
    phase6 = require_phase6_data()
    if phase6 is not None:
        roster = select_completed_roster(
            season,
            bundle["seasons"],
            phase6["roster_snapshots"],
            phase6["roster_players"],
            bundle["season_teams"],
            bundle["assignments"],
        )
        if roster.available:
            st.success(f"Completed roster snapshot available · {len(roster.rows):,} player entries")
            st.caption(
                "Open Drafts for team-level roster detail and the exact snapshot definition."
            )
        else:
            st.info(roster.message)
render_formula_help(readiness)

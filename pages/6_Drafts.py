"""Draft boards, pick history, tendencies, and completed-season rosters."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from fantasy_history.draft_value import (
    DRAFT_PRESENTATION_VERSION,
    build_draft_board,
    build_player_history,
    enrich_draft_picks,
    select_completed_roster,
    summarize_position_allocation,
)
from fantasy_history.ui import (
    apply_app_style,
    require_draft_analytics_data,
    require_phase6_data,
    require_ready_data,
    selected_query_value,
)

st.set_page_config(page_title="Drafts · Fantasy History", page_icon="📝", layout="wide")
apply_app_style()
st.title("Drafts and rosters")
st.caption("Start with the board or report cards; detailed value math stays available on demand.")

loaded = require_ready_data()
phase6 = require_phase6_data()
if loaded is None or phase6 is None:
    st.stop()
_readiness, bundle = loaded
draft_analytics = require_draft_analytics_data()

picks = enrich_draft_picks(
    phase6["draft_picks"],
    phase6["players"],
    bundle["season_teams"],
    bundle["assignments"],
)
drafts = phase6["drafts"].sort_values("season", ascending=False)
if drafts.empty:
    st.info("No draft seasons are available.")
    st.stop()
season_values = [str(int(value)) for value in drafts["season"]]
default = selected_query_value("season", season_values, season_values[0])
selector_key = "draft_season_selector"
query_marker_key = "draft_season_query_value"
if selector_key not in st.session_state:
    st.session_state[query_marker_key] = default
    selector_index: int | None = season_values.index(default)
elif st.session_state.get(query_marker_key) != default:
    st.session_state[selector_key] = default
    st.session_state[query_marker_key] = default
    selector_index = None
else:
    selector_index = None


def sync_draft_query() -> None:
    """Commit the selected draft season to the shareable URL."""
    selected_season = str(st.session_state[selector_key])
    st.query_params["season"] = selected_season
    st.session_state[query_marker_key] = selected_season


selected = st.selectbox(
    "Draft season",
    season_values,
    index=selector_index,
    key=selector_key,
    on_change=sync_draft_query,
)
if selected is None:
    st.stop()
season = int(selected)
draft = drafts[drafts["season"].eq(season)].iloc[0]
season_picks = picks[picks["season"].eq(season)].copy()
named_count = int(season_picks["player_available"].sum())

metrics = st.columns(3)
metrics[0].metric("Recorded picks", f"{len(season_picks):,}")
metrics[1].metric("Players identified", f"{named_count:,} of {len(season_picks):,}")
metrics[2].metric("Rounds", int(season_picks["round"].nunique()))
if not bool(draft["drafted"]) or bool(draft["in_progress"]):
    st.warning(
        "This draft is incomplete. Recorded rows are partial and receive no value labels.",
        icon="⚠️",
    )
elif named_count < len(season_picks):
    st.info(
        "Some drafted players are absent from the retained player metadata. Their names and "
        "positions remain unavailable."
    )

board_tab, picks_tab, history_tab, roster_tab, value_tab = st.tabs(
    ["Draft board", "Pick history", "Tendencies", "Roster snapshot", "Player value"]
)

with board_tab:
    st.subheader(f"{season} draft board")
    board = build_draft_board(picks, season)
    if board.empty:
        st.info("No draft picks are available for this season.")
    else:
        st.dataframe(
            board,
            width="stretch",
            hide_index=True,
            column_config={"Round": st.column_config.NumberColumn("Round", format="%d")},
        )
        st.caption("Columns are source teams, ordered by their first recorded overall pick.")

with picks_tab:
    search = st.text_input("Search picks", placeholder="Player, source team, manager, or position")
    visible = season_picks.copy()
    if search:
        searchable = visible[["player_name", "team_name", "manager_name", "position"]].fillna("")
        mask = searchable.apply(
            lambda column: column.astype(str).str.contains(search, case=False, regex=False)
        ).any(axis=1)
        visible = visible[mask]
    pick_columns = [
        "overall_pick",
        "round",
        "round_pick",
        "player_name",
        "position",
        "team_name",
        "manager_name",
        "is_keeper",
    ]
    st.dataframe(
        visible[pick_columns],
        width="stretch",
        hide_index=True,
        column_config={
            "overall_pick": "Pick",
            "round": "Round",
            "round_pick": "In round",
            "player_name": "Player",
            "position": "Pos.",
            "team_name": "Team",
            "manager_name": "Manager",
            "is_keeper": "Keeper",
        },
    )
    st.download_button(
        "Download filtered picks (CSV)",
        visible[pick_columns].to_csv(index=False, na_rep="").encode("utf-8"),
        file_name=f"fantasy-draft-picks-{season}.csv",
        mime="text/csv",
    )

with history_tab:
    allocation = summarize_position_allocation(picks)
    allocation = allocation[allocation["season"].eq(season)]
    st.subheader("Position allocation")
    if allocation.empty:
        st.info("Position allocation is unavailable because player positions are unavailable.")
    else:
        chart = px.bar(
            allocation,
            x="manager_name",
            y="picks",
            color="position",
            title=f"{season} known-position picks",
            labels={"manager_name": "Manager", "picks": "Picks", "position": "Position"},
        )
        st.plotly_chart(chart, width="stretch")
        st.caption("Shares use only picks with source-supported position metadata.")
    repeated = build_player_history(picks)
    repeated = repeated[repeated["seasons_drafted"].gt(1)]
    st.subheader("Repeated players")
    if repeated.empty:
        st.info("No repeated selections are available.")
    else:
        with st.expander(f"View {len(repeated)} repeated-player histories"):
            st.dataframe(
                repeated[
                    [
                        "manager_name",
                        "player_name",
                        "seasons_drafted",
                        "times_drafted",
                        "seasons",
                        "best_overall_pick",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

with roster_tab:
    st.subheader(f"{season} completed-season roster snapshot")
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
        st.dataframe(
            roster.rows[["team_name", "manager_name", "player_name", "position", "lineup_slot_id"]],
            width="stretch",
            hide_index=True,
            column_config={
                "team_name": "Team",
                "manager_name": "Manager",
                "player_name": "Player",
                "position": "Pos.",
                "lineup_slot_id": "Lineup slot",
            },
        )
        st.caption(
            "Definition: the season_roster snapshot returned by ESPN after the normalized "
            "season is marked complete. It is not a history of every player held. Manual ESPN "
            "reconciliation is still required before Phase 6 exits."
        )

with value_tab:
    st.subheader("Player value")
    if draft_analytics is None:
        st.info("Build the draft analytics bundle to view classifications and report cards.")
    else:
        values = draft_analytics["draft_pick_values"]
        values = values[values["season"].eq(season)].sort_values("overall_pick")
        eligible = values[values["value_eligibility"].eq("eligible")]
        value_metrics = st.columns(4)
        value_metrics[0].metric("Value-eligible", f"{len(eligible)} of {len(values)}")
        value_metrics[1].metric("Booms", int(eligible["value_label"].eq("boom").sum()))
        value_metrics[2].metric("Busts", int(eligible["value_label"].eq("bust").sum()))
        value_metrics[3].metric(
            "Drafted sleepers", int(eligible["value_label"].eq("sleeper").sum())
        )
        cards = draft_analytics["draft_report_cards"]
        cards = cards[cards["season"].eq(season)]
        st.subheader("Draft report cards")
        if cards.empty:
            st.info("Report cards are unavailable for this season.")
        else:
            st.dataframe(
                cards[
                    [
                        "manager_name",
                        "grade",
                        "report_card_score",
                        "eligible_picks",
                        "average_pick_percentile",
                        "total_raw_surplus",
                        "boom_rate",
                        "bust_rate",
                        "steal_rate",
                    ]
                ],
                width="stretch",
                hide_index=True,
                column_config={
                    "manager_name": "Manager",
                    "grade": "Grade",
                    "report_card_score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%.0f"
                    ),
                    "eligible_picks": "Graded picks",
                    "average_pick_percentile": st.column_config.NumberColumn(
                        "Avg. pick percentile", format="%.0f"
                    ),
                    "total_raw_surplus": st.column_config.NumberColumn(
                        "Total surplus", format="%+.1f"
                    ),
                    "boom_rate": st.column_config.NumberColumn("Boom", format="percent"),
                    "bust_rate": st.column_config.NumberColumn("Bust", format="percent"),
                    "steal_rate": st.column_config.NumberColumn("Steal", format="percent"),
                },
            )
        st.subheader("Notable picks")
        notable = values[values["value_label"].isin(["boom", "bust", "sleeper"])].copy()
        if notable.empty:
            st.info("No classified picks are available for this season.")
        else:
            st.dataframe(
                notable[
                    [
                        "overall_pick",
                        "player_name",
                        "position",
                        "manager_name",
                        "actual_fantasy_points",
                        "normalized_surplus",
                        "value_label",
                    ]
                ],
                width="stretch",
                hide_index=True,
                column_config={
                    "overall_pick": "Pick",
                    "player_name": "Player",
                    "position": "Pos.",
                    "manager_name": "Manager",
                    "actual_fantasy_points": st.column_config.NumberColumn("Points", format="%.1f"),
                    "normalized_surplus": st.column_config.NumberColumn(
                        "Value score", format="%+.2f"
                    ),
                    "value_label": "Result",
                },
            )
        baselines = draft_analytics["replacement_baselines"]
        baselines = baselines[baselines["season"].eq(season)]
        with st.expander("All pick values and eligibility"):
            st.dataframe(
                values[
                    [
                        "overall_pick",
                        "round",
                        "player_name",
                        "position",
                        "manager_name",
                        "actual_fantasy_points",
                        "replacement_points",
                        "position_adjusted_value",
                        "expected_position_adjusted_value",
                        "expected_sample_size",
                        "raw_surplus",
                        "normalized_surplus",
                        "value_label",
                        "value_eligibility",
                        "boom_threshold",
                        "bust_threshold",
                        "sleeper_threshold",
                        "late_round_start",
                        "formula_version",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )
        with st.expander("Replacement baselines"):
            st.dataframe(
                baselines[
                    [
                        "position",
                        "replacement_rank",
                        "eligible_position_players",
                        "replacement_points",
                        "baseline_eligibility",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )
        with st.expander("Draft-value formulas and thresholds"):
            st.markdown(
                "- Replacement points are the score at each season/position replacement rank. "
                "Fixed starters set initial demand; FLEX goes to the highest remaining RB/WR/TE "
                "scorers.\n"
                "- Expected value is the median position-adjusted result for the same position, "
                "within 24 overall picks, from other completed seasons; at least 8 samples are "
                "required.\n"
                "- Raw surplus is position-adjusted value minus expected value. Normalized "
                "surplus is its within-season z-score.\n"
                "- Boom: normalized surplus ≥ +1.00. Bust: ≤ -1.00. Drafted sleeper: round 10 "
                "or later, at/above replacement, and normalized surplus ≥ +0.75.\n"
                "- Report-card score is a manager's within-season percentile by average eligible "
                "pick percentile. Grades: A ≥ 80, B ≥ 65, C ≥ 50, D ≥ 35, otherwise F."
            )
            st.caption(
                f"Draft presentation: {DRAFT_PRESENTATION_VERSION} · value formula: "
                "phase6.draft-value.v1"
            )
        with st.expander("Value source trace"):
            st.dataframe(
                values[
                    [
                        "overall_pick",
                        "player_name",
                        "source_row_key",
                        "score_source_row_keys_json",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )
        st.caption(
            "Undrafted sleeper attribution is unavailable because retained ESPN roster rows "
            "do not include acquisition type. Missing production never becomes a bust."
        )

st.caption("No raw ESPN response is read and no ESPN request is made while this page renders.")

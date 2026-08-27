"""Canonical manager profile journey."""

from __future__ import annotations

from typing import Any

import plotly.express as px
import streamlit as st

from fantasy_history.draft_value import (
    attach_final_position_ranks,
    build_player_history,
    enrich_draft_picks,
    select_completed_roster,
    select_manager_notable_picks,
    summarize_position_allocation,
)
from fantasy_history.formatting import format_points, format_record, format_signed
from fantasy_history.ui import (
    aliases_for,
    apply_app_style,
    manager_lookup,
    record_holder_names,
    render_formula_help,
    require_draft_analytics_data,
    require_phase6_data,
    require_ready_data,
    selected_query_value,
)

st.set_page_config(page_title="Managers · Fantasy History", page_icon="👤", layout="wide")
apply_app_style()
st.title("Manager profiles")
st.caption("Choose a manager for the highlights; open the detail sections only when you need them.")

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
st.subheader("Career trend")
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
with st.expander("Season-by-season stat sheet", expanded=True):
    st.caption("Select a season row to reveal that manager's final roster.")
    season_table = (
        seasons[season_columns].sort_values("season", ascending=False).reset_index(drop=True)
    )
    season_event = st.dataframe(
        season_table,
        width="stretch",
        hide_index=True,
        key="manager_season_stat_sheet",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "season": "Season",
            "points_for": st.column_config.NumberColumn("Points", format="%.1f"),
            "official_finish": "Finish",
            "playoff_seed": "Seed",
            "playoff_appearance": "Playoffs",
            "championship": "Champion",
            "runner_up": "Runner-up",
            "expected_wins": st.column_config.NumberColumn("Expected wins", format="%.1f"),
            "luck_differential": st.column_config.NumberColumn("Luck", format="%+.1f"),
        },
    )
    selected_rows = season_event.selection.rows
    if selected_rows:
        selected_season = int(season_table.iloc[selected_rows[0]]["season"])
        st.markdown(f"#### {selected_season} final roster")
        roster_inputs = require_phase6_data()
        if roster_inputs is not None:
            roster = select_completed_roster(
                selected_season,
                bundle["seasons"],
                roster_inputs["roster_snapshots"],
                roster_inputs["roster_players"],
                bundle["season_teams"],
                bundle["assignments"],
            )
            if not roster.available:
                st.info(roster.message)
            else:
                assigned_team_ids = set(
                    bundle["assignments"].loc[
                        bundle["assignments"]["season"].eq(selected_season)
                        & bundle["assignments"]["canonical_manager_id"].astype(str).eq(manager_id),
                        "source_team_id",
                    ]
                )
                manager_roster = roster.rows[roster.rows["source_team_id"].isin(assigned_team_ids)]
                if manager_roster.empty:
                    st.info("No final-roster rows are attributed to this manager for that season.")
                else:
                    manager_roster = attach_final_position_ranks(
                        manager_roster,
                        roster_inputs["player_scores"],
                        roster_inputs["players"],
                        bundle["seasons"],
                    ).sort_values(["lineup_slot_id", "player_name"], kind="stable")
                    st.dataframe(
                        manager_roster[
                            ["player_name", "position", "final_position_rank", "team_name"]
                        ],
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "player_name": "Player",
                            "position": "Pos.",
                            "final_position_rank": st.column_config.NumberColumn(
                                "Final positional rank", format="%d"
                            ),
                            "team_name": "Team",
                        },
                    )
                    st.caption(
                        "This is ESPN's completed-season roster snapshot, not every player held "
                        "during the season. Rows remain ordered by ESPN's final lineup slot; "
                        "positional rank uses actual season-total fantasy points."
                    )

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
    with st.expander("All opponent records"):
        st.dataframe(
            head[opponent_columns].sort_values("meetings", ascending=False),
            width="stretch",
            hide_index=True,
            column_config={
                "opponent": "Opponent",
                "points_for": st.column_config.NumberColumn("Points for", format="%.1f"),
                "points_against": st.column_config.NumberColumn("Points against", format="%.1f"),
                "point_differential": st.column_config.NumberColumn("Point diff.", format="%+.1f"),
                "average_margin": st.column_config.NumberColumn("Avg. margin", format="%+.1f"),
                "closest_margin": st.column_config.NumberColumn("Closest", format="%.1f"),
            },
        )

held = record_holder_names(bundle["records"], bundle)
held = held[held["canonical_manager_id"].astype("string").eq(manager_id)]
st.subheader("Records held")
if held.empty:
    st.caption("No manager-level league records currently held.")
else:
    with st.expander(f"View {len(held)} record(s)"):
        st.dataframe(held[["category_label", "value", "season"]], width="stretch", hide_index=True)

st.subheader("Draft tendencies")
phase6 = require_phase6_data()
if phase6 is not None:
    picks = enrich_draft_picks(
        phase6["draft_picks"],
        phase6["players"],
        bundle["season_teams"],
        bundle["assignments"],
    )
    allocation = summarize_position_allocation(picks)
    allocation = allocation[allocation["canonical_manager_id"].astype(str).eq(manager_id)]
    if allocation.empty:
        st.caption("Known-position draft tendencies are unavailable.")
    else:
        totals = allocation.groupby("position", as_index=False).agg(picks=("picks", "sum"))
        position_chart = px.bar(
            totals.sort_values("picks", ascending=False),
            x="position",
            y="picks",
            title="Career picks by position",
            labels={"position": "Position", "picks": "Picks"},
        )
        position_chart.update_layout(showlegend=False, margin=dict(l=0, r=0, t=45, b=0))
        st.plotly_chart(position_chart, width="stretch")
    repeated = build_player_history(picks)
    repeated = repeated[
        repeated["canonical_manager_id"].astype(str).eq(manager_id)
        & repeated["seasons_drafted"].gt(1)
    ]
    if repeated.empty:
        st.caption("No repeated player selections are available.")
    else:
        with st.expander("Repeated player selections"):
            st.dataframe(
                repeated[
                    [
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
    draft_analytics = require_draft_analytics_data()
    if draft_analytics is not None:
        values = draft_analytics["draft_pick_values"]
        sleepers = select_manager_notable_picks(values, manager_id, "sleeper")
        busts = select_manager_notable_picks(values, manager_id, "bust")
        st.markdown("#### Biggest drafted sleepers and busts")
        notable_columns = [
            "player_name",
            "season",
            "round",
            "overall_pick",
            "position",
            "actual_fantasy_points",
            "normalized_surplus",
        ]
        notable_config: dict[str, Any] = {
            "player_name": "Player",
            "season": "Season",
            "round": "Rd.",
            "overall_pick": "Pick",
            "position": "Pos.",
            "actual_fantasy_points": st.column_config.NumberColumn("Points", format="%.1f"),
            "normalized_surplus": st.column_config.NumberColumn("Value score", format="%+.2f"),
        }
        sleeper_column, bust_column = st.columns(2)
        with sleeper_column:
            st.markdown("**Sleepers**")
            if sleepers.empty:
                st.caption("No drafted sleepers meet the current threshold.")
            else:
                st.dataframe(
                    sleepers[notable_columns],
                    width="stretch",
                    hide_index=True,
                    column_config=notable_config,
                )
        with bust_column:
            st.markdown("**Busts**")
            if busts.empty:
                st.caption("No busts meet the current threshold.")
            else:
                st.dataframe(
                    busts[notable_columns],
                    width="stretch",
                    hide_index=True,
                    column_config=notable_config,
                )
        st.caption(
            "Career top five by within-season normalized surplus. Sleepers are round 10 or "
            "later; undrafted sleeper attribution is unavailable."
        )

        cards = draft_analytics["draft_report_cards"]
        cards = cards[cards["canonical_manager_id"].astype(str).eq(manager_id)]
        if not cards.empty:
            latest_card = cards.sort_values("season", ascending=False).iloc[0]
            card_metrics = st.columns(3)
            card_metrics[0].metric(
                f"{int(latest_card['season'])} draft grade", str(latest_card["grade"])
            )
            card_metrics[1].metric("Boom rate", f"{float(latest_card['boom_rate']):.0%}")
            card_metrics[2].metric("Bust rate", f"{float(latest_card['bust_rate']):.0%}")
            with st.expander("All draft report cards"):
                st.dataframe(
                    cards[
                        [
                            "season",
                            "grade",
                            "report_card_score",
                            "eligible_picks",
                            "average_normalized_surplus",
                            "boom_rate",
                            "bust_rate",
                            "steal_rate",
                        ]
                    ].sort_values("season", ascending=False),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "report_card_score": st.column_config.NumberColumn("Score", format="%.0f"),
                        "average_normalized_surplus": st.column_config.NumberColumn(
                            "Avg. surplus", format="%+.2f"
                        ),
                        "boom_rate": st.column_config.NumberColumn("Boom rate", format="percent"),
                        "bust_rate": st.column_config.NumberColumn("Bust rate", format="percent"),
                        "steal_rate": st.column_config.NumberColumn("Steal rate", format="percent"),
                    },
                )

render_formula_help(readiness)

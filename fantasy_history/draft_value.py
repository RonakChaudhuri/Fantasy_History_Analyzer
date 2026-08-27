"""Source-traceable draft and completed-season roster presentation analytics."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

DRAFT_PRESENTATION_VERSION = "phase6.draft-presentation.v1"
PRODUCTION_FORMULA_VERSION = "phase6.actual-season-total.v1"
DRAFT_VALUE_FORMULA_VERSION = "phase6.draft-value.v1"
EXPECTED_PICK_WINDOW = 24
EXPECTED_MIN_SAMPLE = 8
BOOM_THRESHOLD = 1.0
BUST_THRESHOLD = -1.0
SLEEPER_THRESHOLD = 0.75
LATE_ROUND_START = 10

FIXED_STARTER_SLOTS = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K"}
FLEX_SLOT_ID = 23
SUPERFLEX_SLOT_ID = 7
FLEX_POSITIONS = ("RB", "WR", "TE")
SUPERFLEX_POSITIONS = ("QB", "RB", "WR", "TE")

# ESPN default-position identifiers retained in normalized data. Unknown identifiers
# stay visible instead of being guessed into a football position.
POSITION_LABELS = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}


@dataclass(frozen=True)
class RosterSelection:
    """Availability and rows for one completed-season roster snapshot."""

    status: str
    message: str
    rows: pd.DataFrame

    @property
    def available(self) -> bool:
        """Whether the snapshot may be displayed as completed-season roster data."""
        return self.status == "available"


def _manager_attribution(assignments: pd.DataFrame) -> pd.DataFrame:
    """Collapse deliberate multi-manager attribution without duplicating pick rows."""
    keys = ["league_id", "season", "source_team_id"]
    required = [*keys, "canonical_manager_id", "canonical_display_name"]
    selected = assignments[required].drop_duplicates()
    if selected.empty:
        return pd.DataFrame(columns=[*keys, "canonical_manager_id", "manager_name"])

    def joined(values: pd.Series) -> str:
        return " / ".join(sorted({str(value) for value in values.dropna()}))

    return (
        selected.groupby(keys, as_index=False)
        .agg(
            canonical_manager_id=("canonical_manager_id", joined),
            manager_name=("canonical_display_name", joined),
        )
        .sort_values(keys, kind="stable")
    )


def enrich_draft_picks(
    picks: pd.DataFrame,
    players: pd.DataFrame,
    season_teams: pd.DataFrame,
    assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Join pick cost to reviewed team attribution and available player metadata."""
    player_columns = [
        "league_id",
        "season",
        "source_player_id",
        "full_name",
        "default_position_id",
    ]
    team_columns = ["league_id", "season", "source_team_id", "team_name"]
    result = picks.merge(
        players[player_columns].drop_duplicates(
            ["league_id", "season", "source_player_id"], keep="last"
        ),
        on=["league_id", "season", "source_player_id"],
        how="left",
        validate="many_to_one",
    )
    result["player_name"] = result["player_name"].combine_first(result["full_name"])
    result = result.drop(columns="full_name")
    result = result.merge(
        season_teams[team_columns].drop_duplicates(team_columns[:3]),
        on=["league_id", "season", "source_team_id"],
        how="left",
        validate="many_to_one",
    ).merge(
        _manager_attribution(assignments),
        on=["league_id", "season", "source_team_id"],
        how="left",
        validate="many_to_one",
    )
    position_ids = pd.to_numeric(result["default_position_id"], errors="coerce").astype("Int64")
    result["position"] = position_ids.map(POSITION_LABELS).fillna(
        position_ids.map(lambda value: f"Position {value}" if pd.notna(value) else pd.NA)
    )
    result["player_available"] = result["player_name"].notna()
    result["presentation_version"] = DRAFT_PRESENTATION_VERSION
    return result.sort_values(["season", "overall_pick"], kind="stable")


def build_draft_board(picks: pd.DataFrame, season: int) -> pd.DataFrame:
    """Build a round-by-source-team board in actual overall-pick order."""
    selected = picks[picks["season"].eq(season)].sort_values("overall_pick", kind="stable").copy()
    if selected.empty:
        return pd.DataFrame()
    selected["team_label"] = selected["team_name"].combine_first(selected["manager_name"])
    selected["team_label"] = selected["team_label"].fillna("Unavailable team")
    selected["pick_label"] = selected["player_name"].fillna("Unavailable player")
    selected["pick_label"] = (
        selected["overall_pick"].astype("Int64").astype("string")
        + ". "
        + selected["pick_label"].astype("string")
    )
    selected.loc[selected["is_keeper"].fillna(False), "pick_label"] += " (keeper)"
    team_order = (
        selected.groupby("team_label", as_index=False)["overall_pick"]
        .min()
        .sort_values("overall_pick", kind="stable")["team_label"]
        .tolist()
    )
    grouped = (
        selected.groupby(["round", "team_label"], sort=False)["pick_label"]
        .agg(" · ".join)
        .unstack("team_label")
    )
    grouped = grouped.reindex(columns=team_order).sort_index(kind="stable")
    grouped.index.name = "Round"
    return grouped.reset_index()


def summarize_position_allocation(picks: pd.DataFrame) -> pd.DataFrame:
    """Count source-supported positions by manager and season."""
    eligible = picks[picks["position"].notna() & picks["canonical_manager_id"].notna()].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "canonical_manager_id",
                "manager_name",
                "position",
                "picks",
                "known_position_share",
            ]
        )
    grouped = (
        eligible.groupby(
            ["season", "canonical_manager_id", "manager_name", "position"], as_index=False
        )
        .agg(picks=("source_pick_id", "size"))
        .sort_values(["season", "manager_name", "position"], kind="stable")
    )
    totals = grouped.groupby(["season", "canonical_manager_id"])["picks"].transform("sum")
    grouped["known_position_share"] = grouped["picks"] / totals
    return grouped


def attach_actual_production(
    picks: pd.DataFrame, player_scores: pd.DataFrame, seasons: pd.DataFrame
) -> pd.DataFrame:
    """Attach deduplicated actual season totals without summing repeated observations."""
    score_keys = ["league_id", "season", "source_player_id"]
    eligible_scores = player_scores[
        player_scores["stat_source"].eq("actual")
        & player_scores["score_scope"].eq("season_total")
        & player_scores["availability"].eq("available")
        & player_scores["score_season"].eq(player_scores["season"])
        & player_scores["applied_fantasy_points"].notna()
    ].copy()

    def summarize(group: pd.DataFrame) -> pd.Series:
        values = group["applied_fantasy_points"].dropna().astype(float).unique()
        source_keys = sorted(set(group["source_row_key"].dropna().astype(str)))
        return pd.Series(
            {
                "actual_fantasy_points": values[0] if len(values) == 1 else pd.NA,
                "production_eligibility": (
                    "eligible" if len(values) == 1 else "conflicting_actual_season_totals"
                ),
                "score_source_row_keys_json": json.dumps(source_keys, separators=(",", ":")),
                "score_observation_count": len(group),
            }
        )

    if eligible_scores.empty:
        production = pd.DataFrame(
            columns=[
                *score_keys,
                "actual_fantasy_points",
                "production_eligibility",
                "score_source_row_keys_json",
                "score_observation_count",
            ]
        )
    else:
        production = (
            eligible_scores.groupby(score_keys, as_index=False, dropna=False)
            .apply(summarize, include_groups=False)
            .reset_index(drop=True)
        )
    result = picks.merge(production, on=score_keys, how="left", validate="many_to_one")
    result["production_eligibility"] = result["production_eligibility"].fillna(
        "missing_actual_season_total"
    )
    result.loc[result["source_player_id"].isna(), "production_eligibility"] = (
        "missing_source_player"
    )
    active_seasons = set(seasons.loc[seasons["is_active"].fillna(False), "season"])
    result.loc[result["season"].isin(active_seasons), "production_eligibility"] = "active_season"
    result.loc[~result["production_eligibility"].eq("eligible"), "actual_fantasy_points"] = pd.NA
    result["production_formula_version"] = PRODUCTION_FORMULA_VERSION
    return result


def production_coverage_by_season(picks: pd.DataFrame) -> pd.DataFrame:
    """Report honest denominators for source-supported player production."""
    if picks.empty:
        return pd.DataFrame(columns=["season", "total_picks", "eligible_picks", "eligible_share"])
    coverage = picks.groupby("season", as_index=False).agg(
        total_picks=("source_pick_id", "size"),
        eligible_picks=(
            "production_eligibility",
            lambda values: values.eq("eligible").sum(),
        ),
    )
    coverage["eligible_share"] = coverage["eligible_picks"] / coverage["total_picks"]
    return coverage.sort_values("season", kind="stable")


def build_actual_player_pool(
    player_scores: pd.DataFrame, players: pd.DataFrame, seasons: pd.DataFrame
) -> pd.DataFrame:
    """Build one deduplicated actual season-total row per observed player season."""
    observed = player_scores[
        player_scores["source_player_id"].notna()
        & player_scores["score_season"].eq(player_scores["season"])
    ][["league_id", "season", "source_player_id"]].drop_duplicates()
    synthetic_picks = observed.assign(source_pick_id=pd.NA)
    production = attach_actual_production(synthetic_picks, player_scores, seasons)
    metadata = players[
        ["league_id", "season", "source_player_id", "full_name", "default_position_id"]
    ].drop_duplicates(["league_id", "season", "source_player_id"], keep="last")
    production = production.merge(
        metadata,
        on=["league_id", "season", "source_player_id"],
        how="left",
        validate="one_to_one",
    )
    position_ids = pd.to_numeric(production["default_position_id"], errors="coerce").astype("Int64")
    production["position"] = position_ids.map(POSITION_LABELS).fillna(
        position_ids.map(lambda value: f"Position {value}" if pd.notna(value) else pd.NA)
    )
    return production


def attach_final_position_ranks(
    roster_rows: pd.DataFrame,
    player_scores: pd.DataFrame,
    players: pd.DataFrame,
    seasons: pd.DataFrame,
) -> pd.DataFrame:
    """Attach source-supported final season rank within each player's position."""
    result = roster_rows.copy()
    result["final_position_rank"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    if result.empty:
        return result

    player_pool = build_actual_player_pool(player_scores, players, seasons)
    eligible = player_pool[
        player_pool["production_eligibility"].eq("eligible")
        & player_pool["position"].notna()
        & player_pool["actual_fantasy_points"].notna()
    ].copy()
    if eligible.empty:
        return result

    eligible["final_position_rank"] = (
        eligible.groupby(["league_id", "season", "position"])["actual_fantasy_points"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    ranks = eligible[
        ["league_id", "season", "source_player_id", "final_position_rank"]
    ].drop_duplicates(["league_id", "season", "source_player_id"], keep="last")
    result = result.drop(columns="final_position_rank").merge(
        ranks,
        on=["league_id", "season", "source_player_id"],
        how="left",
        validate="many_to_one",
    )
    result["final_position_rank"] = result["final_position_rank"].astype("Int64")
    return result


def _allocate_flexible_demand(
    demand: dict[str, int],
    eligible: pd.DataFrame,
    slot_counts: dict[int, int],
    team_count: int,
    slot_id: int,
    positions: tuple[str, ...],
) -> None:
    """Allocate flexible starters to the highest remaining eligible scorers."""
    flex_demand = team_count * slot_counts.get(slot_id, 0)
    if flex_demand <= 0:
        return
    candidates = []
    for position in positions:
        position_pool = eligible[eligible["position"].eq(position)].sort_values(
            "actual_fantasy_points", ascending=False, kind="stable"
        )
        candidates.append(position_pool.iloc[demand.get(position, 0) :])
    available = pd.concat(candidates, ignore_index=True) if candidates else pd.DataFrame()
    if available.empty:
        return
    selected = available.nlargest(flex_demand, "actual_fantasy_points")
    allocations = selected["position"].value_counts()
    for position, count in allocations.items():
        demand[str(position)] = demand.get(str(position), 0) + int(count)


def calculate_replacement_baselines(
    player_pool: pd.DataFrame,
    seasons: pd.DataFrame,
    season_teams: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate season/position replacement points from fixed and flex starter demand."""
    rows: list[dict[str, object]] = []
    completed = seasons[~seasons["is_active"].fillna(False)]
    for season_row in completed.itertuples(index=False):
        season = int(season_row.season)
        league_id = int(season_row.league_id)
        team_count = int(
            season_teams[
                season_teams["season"].eq(season) & season_teams["league_id"].eq(league_id)
            ]["source_team_id"].nunique()
        )
        slot_counts = {
            int(key): int(value)
            for key, value in json.loads(str(season_row.lineup_slot_counts_json)).items()
        }
        eligible = player_pool[
            player_pool["season"].eq(season)
            & player_pool["league_id"].eq(league_id)
            & player_pool["production_eligibility"].eq("eligible")
            & player_pool["position"].isin(POSITION_LABELS.values())
        ].copy()
        eligible["actual_fantasy_points"] = pd.to_numeric(
            eligible["actual_fantasy_points"], errors="coerce"
        )
        eligible = eligible[eligible["actual_fantasy_points"].notna()]
        demand = {
            position: team_count * slot_counts.get(slot_id, 0)
            for slot_id, position in FIXED_STARTER_SLOTS.items()
        }

        _allocate_flexible_demand(
            demand, eligible, slot_counts, team_count, FLEX_SLOT_ID, FLEX_POSITIONS
        )
        _allocate_flexible_demand(
            demand, eligible, slot_counts, team_count, SUPERFLEX_SLOT_ID, SUPERFLEX_POSITIONS
        )
        for position in FIXED_STARTER_SLOTS.values():
            position_pool = eligible[eligible["position"].eq(position)].sort_values(
                "actual_fantasy_points", ascending=False, kind="stable"
            )
            replacement_rank = demand.get(position, 0)
            baseline_available = replacement_rank > 0 and len(position_pool) >= replacement_rank
            baseline = (
                float(position_pool.iloc[replacement_rank - 1]["actual_fantasy_points"])
                if baseline_available
                else pd.NA
            )
            rows.append(
                {
                    "league_id": league_id,
                    "season": season,
                    "position": position,
                    "team_count": team_count,
                    "replacement_rank": replacement_rank,
                    "eligible_position_players": len(position_pool),
                    "replacement_points": baseline,
                    "baseline_eligibility": (
                        "eligible" if baseline_available else "insufficient_position_pool"
                    ),
                    "formula_version": DRAFT_VALUE_FORMULA_VERSION,
                }
            )
    return pd.DataFrame(rows)


def classify_draft_values(values: pd.DataFrame) -> pd.DataFrame:
    """Apply the documented boom, bust, and drafted-sleeper thresholds."""
    result = values.copy()
    label_ready = result["value_eligibility"].eq("eligible")
    result["value_label"] = "unavailable"
    result.loc[label_ready, "value_label"] = "neutral"
    result.loc[label_ready & result["normalized_surplus"].ge(BOOM_THRESHOLD), "value_label"] = (
        "boom"
    )
    result.loc[label_ready & result["normalized_surplus"].le(BUST_THRESHOLD), "value_label"] = (
        "bust"
    )
    sleeper = (
        label_ready
        & result["round"].ge(LATE_ROUND_START)
        & result["position_adjusted_value"].ge(0)
        & result["normalized_surplus"].ge(SLEEPER_THRESHOLD)
    )
    result.loc[sleeper, "value_label"] = "sleeper"
    result["boom_threshold"] = BOOM_THRESHOLD
    result["bust_threshold"] = BUST_THRESHOLD
    result["sleeper_threshold"] = SLEEPER_THRESHOLD
    result["late_round_start"] = LATE_ROUND_START
    return result


def calculate_draft_pick_values(
    picks: pd.DataFrame,
    player_scores: pd.DataFrame,
    players: pd.DataFrame,
    seasons: pd.DataFrame,
    season_teams: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate baselines, leave-one-season-out expected value, surplus, and labels."""
    player_pool = build_actual_player_pool(player_scores, players, seasons)
    baselines = calculate_replacement_baselines(player_pool, seasons, season_teams)
    values = attach_actual_production(picks, player_scores, seasons).merge(
        baselines[
            [
                "league_id",
                "season",
                "position",
                "replacement_rank",
                "replacement_points",
                "baseline_eligibility",
            ]
        ],
        on=["league_id", "season", "position"],
        how="left",
        validate="many_to_one",
    )
    values["value_eligibility"] = values["production_eligibility"]
    values.loc[
        values["production_eligibility"].eq("eligible") & values["position"].isna(),
        "value_eligibility",
    ] = "missing_position"
    values.loc[
        values["production_eligibility"].eq("eligible")
        & values["position"].notna()
        & ~values["baseline_eligibility"].eq("eligible"),
        "value_eligibility",
    ] = "missing_replacement_baseline"
    baseline_ready = values["value_eligibility"].eq("eligible")
    values["position_adjusted_value"] = pd.NA
    values.loc[baseline_ready, "position_adjusted_value"] = values.loc[
        baseline_ready, "actual_fantasy_points"
    ].astype(float) - values.loc[baseline_ready, "replacement_points"].astype(float)
    values["expected_position_adjusted_value"] = pd.NA
    values["expected_sample_size"] = pd.NA
    historical = values[baseline_ready].copy()
    for index, row in historical.iterrows():
        comparison = historical[
            historical["position"].eq(row["position"])
            & historical["season"].ne(row["season"])
            & historical["overall_pick"].sub(row["overall_pick"]).abs().le(EXPECTED_PICK_WINDOW)
        ]
        values.at[index, "expected_sample_size"] = len(comparison)
        if len(comparison) >= EXPECTED_MIN_SAMPLE:
            values.at[index, "expected_position_adjusted_value"] = float(
                comparison["position_adjusted_value"].astype(float).median()
            )
        else:
            values.at[index, "value_eligibility"] = "sparse_expected_value_sample"
    expected_ready = values["value_eligibility"].eq("eligible")
    values["raw_surplus"] = pd.NA
    values.loc[expected_ready, "raw_surplus"] = values.loc[
        expected_ready, "position_adjusted_value"
    ].astype(float) - values.loc[expected_ready, "expected_position_adjusted_value"].astype(float)
    values["normalized_surplus"] = pd.NA
    for _season, group in values[expected_ready].groupby("season"):
        surplus = group["raw_surplus"].astype(float)
        standard_deviation = float(surplus.std(ddof=0))
        if standard_deviation == 0 or pd.isna(standard_deviation):
            values.loc[group.index, "value_eligibility"] = "season_surplus_not_variable"
            continue
        values.loc[group.index, "normalized_surplus"] = (
            surplus - float(surplus.mean())
        ) / standard_deviation
    values = classify_draft_values(values)
    values["formula_version"] = DRAFT_VALUE_FORMULA_VERSION
    return values, baselines


def build_draft_report_cards(values: pd.DataFrame) -> pd.DataFrame:
    """Grade manager seasons from the mean within-season percentile of eligible picks."""
    eligible = values[values["value_eligibility"].eq("eligible")].copy()
    if eligible.empty:
        return pd.DataFrame()
    eligible["pick_percentile_score"] = (
        eligible.groupby("season")["raw_surplus"].rank(pct=True, method="average") * 100
    )
    cards = eligible.groupby(
        ["league_id", "season", "canonical_manager_id", "manager_name"], as_index=False
    ).agg(
        eligible_picks=("source_pick_id", "size"),
        total_raw_surplus=("raw_surplus", "sum"),
        average_normalized_surplus=("normalized_surplus", "mean"),
        boom_count=("value_label", lambda values: values.eq("boom").sum()),
        bust_count=("value_label", lambda values: values.eq("bust").sum()),
        sleeper_count=("value_label", lambda values: values.eq("sleeper").sum()),
        average_pick_percentile=("pick_percentile_score", "mean"),
    )
    cards["boom_rate"] = cards["boom_count"] / cards["eligible_picks"]
    cards["bust_rate"] = cards["bust_count"] / cards["eligible_picks"]
    cards["steal_rate"] = (cards["boom_count"] + cards["sleeper_count"]) / cards["eligible_picks"]
    cards["report_card_score"] = (
        cards.groupby("season")["average_pick_percentile"].rank(pct=True, method="average") * 100
    )
    cards["grade"] = pd.cut(
        cards["report_card_score"],
        bins=[-float("inf"), 35, 50, 65, 80, float("inf")],
        labels=["F", "D", "C", "B", "A"],
        right=False,
    ).astype("string")
    cards["formula_version"] = DRAFT_VALUE_FORMULA_VERSION
    return cards.sort_values(["season", "report_card_score"], ascending=[True, False])


def build_player_history(picks: pd.DataFrame) -> pd.DataFrame:
    """Summarize repeat selections using stable player IDs across seasons."""
    eligible = picks[
        picks["source_player_id"].notna() & picks["canonical_manager_id"].notna()
    ].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "canonical_manager_id",
                "manager_name",
                "source_player_id",
                "player_name",
                "seasons_drafted",
                "times_drafted",
                "seasons",
                "best_overall_pick",
            ]
        )
    eligible = eligible.sort_values("season", kind="stable")

    def latest_available(values: pd.Series) -> str:
        available = values.dropna().astype(str)
        return available.iloc[-1] if not available.empty else "Unavailable"

    history = (
        eligible.groupby(
            ["canonical_manager_id", "source_player_id"],
            as_index=False,
            dropna=False,
        )
        .agg(
            manager_name=("manager_name", latest_available),
            player_name=("player_name", latest_available),
            seasons_drafted=("season", "nunique"),
            times_drafted=("source_pick_id", "size"),
            seasons=("season", lambda values: ", ".join(map(str, sorted(set(values))))),
            best_overall_pick=("overall_pick", "min"),
        )
        .sort_values(
            ["seasons_drafted", "times_drafted", "manager_name", "player_name"],
            ascending=[False, False, True, True],
            kind="stable",
        )
    )
    return history


def select_completed_roster(
    season: int,
    seasons: pd.DataFrame,
    snapshots: pd.DataFrame,
    roster_players: pd.DataFrame,
    season_teams: pd.DataFrame,
    assignments: pd.DataFrame,
) -> RosterSelection:
    """Select the documented season-roster snapshot without treating gaps as empty."""
    season_rows = seasons[seasons["season"].eq(season)]
    empty = pd.DataFrame()
    if season_rows.empty:
        return RosterSelection("missing_season", "Season metadata is unavailable.", empty)
    if bool(season_rows.iloc[0]["is_active"]):
        return RosterSelection(
            "active_season",
            "This season is active, so its roster snapshot is not a final roster.",
            empty,
        )
    selected_snapshots = snapshots[
        snapshots["season"].eq(season) & snapshots["snapshot_type"].eq("season_roster")
    ].copy()
    expected_team_ids = set(
        season_teams.loc[season_teams["season"].eq(season), "source_team_id"].dropna()
    )
    actual_team_ids = set(selected_snapshots["source_team_id"].dropna())
    if selected_snapshots.empty or actual_team_ids != expected_team_ids:
        return RosterSelection(
            "missing_snapshot", "A complete roster snapshot is unavailable.", empty
        )
    if (
        not selected_snapshots["coverage_status"].eq("complete").all()
        or not selected_snapshots["entry_count"].gt(0).all()
    ):
        return RosterSelection(
            "incomplete_snapshot",
            "The roster snapshot is empty or incomplete and is not treated as a final roster.",
            empty,
        )
    rows = roster_players[
        roster_players["season"].eq(season) & roster_players["snapshot_type"].eq("season_roster")
    ].copy()
    if rows.empty:
        return RosterSelection(
            "incomplete_snapshot", "Roster membership rows are unavailable.", empty
        )
    actual_counts = rows.groupby("source_team_id").size()
    expected_counts = selected_snapshots.set_index("source_team_id")["entry_count"]
    if not actual_counts.reindex(expected_counts.index).eq(expected_counts).all():
        return RosterSelection(
            "incomplete_snapshot",
            "Roster membership rows do not match the declared snapshot counts.",
            empty,
        )
    if "source_row_key" not in rows or rows["source_row_key"].isna().any():
        return RosterSelection(
            "incomplete_snapshot", "Roster membership lacks source traceability.", empty
        )
    rows = rows.merge(
        season_teams[["league_id", "season", "source_team_id", "team_name"]].drop_duplicates(
            ["league_id", "season", "source_team_id"]
        ),
        on=["league_id", "season", "source_team_id"],
        how="left",
        validate="many_to_one",
    ).merge(
        _manager_attribution(assignments),
        on=["league_id", "season", "source_team_id"],
        how="left",
        validate="many_to_one",
    )
    position_ids = pd.to_numeric(rows["default_position_id"], errors="coerce").astype("Int64")
    rows["position"] = position_ids.map(POSITION_LABELS).fillna(
        position_ids.map(lambda value: f"Position {value}" if pd.notna(value) else pd.NA)
    )
    rows["presentation_version"] = DRAFT_PRESENTATION_VERSION
    rows = rows.sort_values(["team_name", "lineup_slot_id", "player_name"], kind="stable")
    return RosterSelection(
        "available",
        "Completed-season roster snapshot available.",
        rows,
    )

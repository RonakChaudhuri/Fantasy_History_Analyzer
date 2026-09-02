"""Pure presentation joins for source-traceable completed trade history."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def _asset_label(row: pd.Series) -> str:
    name = row.get("full_name")
    if pd.notna(name) and str(name).strip():
        return str(name)
    overall = row.get("overall_pick")
    if pd.notna(overall):
        return f"Draft pick #{int(overall)}"
    player_id = row.get("source_player_id")
    return f"Player #{int(player_id)}" if pd.notna(player_id) else "Unknown asset"


def build_trade_history(
    trades: pd.DataFrame,
    trade_items: pd.DataFrame,
    players: pd.DataFrame,
    season_teams: pd.DataFrame,
    assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve completed trades to player, team, and canonical-manager labels."""
    columns = [
        "source_trade_id",
        "season",
        "scoring_period",
        "trade_date",
        "participant_manager_ids",
        "managers",
        "deal",
    ]
    if trades.empty or trade_items.empty:
        return pd.DataFrame(columns=columns)

    player_names = (
        players[["season", "source_player_id", "full_name"]]
        .dropna(subset=["source_player_id"])
        .sort_values(["season", "source_player_id", "full_name"], na_position="last")
        .drop_duplicates(["season", "source_player_id"])
    )
    items = trade_items.merge(player_names, on=["season", "source_player_id"], how="left").copy()
    items["asset"] = items.apply(_asset_label, axis=1)

    team_names = season_teams[["season", "source_team_id", "team_name"]].drop_duplicates()
    manager_groups = (
        assignments.groupby(["season", "source_team_id"], dropna=False)
        .agg(
            manager_ids=(
                "canonical_manager_id",
                lambda values: tuple(sorted({str(value) for value in values.dropna()})),
            ),
            manager_names=(
                "canonical_display_name",
                lambda values: " & ".join(sorted({str(value) for value in values.dropna()})),
            ),
        )
        .reset_index()
        .merge(team_names, on=["season", "source_team_id"], how="left")
    )
    team_lookup: dict[tuple[int, int], tuple[tuple[str, ...], str]] = {}
    for row in manager_groups.itertuples(index=False):
        label = row.manager_names or row.team_name or f"Team {int(row.source_team_id)}"
        team_lookup[(int(row.season), int(row.source_team_id))] = (
            tuple(row.manager_ids),
            str(label),
        )

    rows: list[dict[str, Any]] = []
    for trade in trades.itertuples(index=False):
        trade_assets = items[
            items["season"].eq(trade.season) & items["source_trade_id"].eq(trade.source_trade_id)
        ]
        received: defaultdict[int, list[str]] = defaultdict(list)
        team_ids: set[int] = set()
        for item in trade_assets.itertuples(index=False):
            if pd.notna(item.from_team_id):
                team_ids.add(int(item.from_team_id))
            if pd.notna(item.to_team_id):
                team_id = int(item.to_team_id)
                team_ids.add(team_id)
                received[team_id].append(str(item.asset))
        participant_ids: set[str] = set()
        participant_names: list[str] = []
        deal_parts: list[str] = []
        for team_id in sorted(team_ids):
            manager_ids, label = team_lookup.get(
                (int(trade.season), team_id), ((), f"Team {team_id}")
            )
            participant_ids.update(manager_ids)
            participant_names.append(label)
            assets = ", ".join(sorted(received.get(team_id, ["No listed assets"])))
            deal_parts.append(f"{label} received {assets}")
        timestamp = pd.to_datetime(
            trade.executed_date_epoch_ms, unit="ms", utc=True, errors="coerce"
        )
        rows.append(
            {
                "source_trade_id": str(trade.source_trade_id),
                "season": int(trade.season),
                "scoring_period": trade.scoring_period,
                "trade_date": timestamp.date() if pd.notna(timestamp) else pd.NaT,
                "participant_manager_ids": tuple(sorted(participant_ids)),
                "managers": " ↔ ".join(participant_names),
                "deal": "; ".join(deal_parts),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["season", "scoring_period", "trade_date"],
        ascending=[False, False, False],
        na_position="last",
        kind="stable",
    )


def manager_trade_history(history: pd.DataFrame, manager_id: str) -> pd.DataFrame:
    """Select trades involving one canonical manager without merging identities."""
    if history.empty:
        return history.copy()
    return history[
        history["participant_manager_ids"].map(lambda values: manager_id in values)
    ].copy()

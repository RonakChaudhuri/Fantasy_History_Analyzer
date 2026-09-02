from __future__ import annotations

import pandas as pd

from fantasy_history.trades import build_trade_history, manager_trade_history


def test_trade_history_resolves_canonical_managers_and_player_names() -> None:
    trades = pd.DataFrame(
        [
            {
                "source_trade_id": "trade-1",
                "season": 2025,
                "scoring_period": 4,
                "executed_date_epoch_ms": 1_750_000_000_000,
            }
        ]
    )
    items = pd.DataFrame(
        [
            {
                "source_trade_id": "trade-1",
                "season": 2025,
                "source_player_id": 10,
                "overall_pick": pd.NA,
                "from_team_id": 1,
                "to_team_id": 2,
            },
            {
                "source_trade_id": "trade-1",
                "season": 2025,
                "source_player_id": 20,
                "overall_pick": pd.NA,
                "from_team_id": 2,
                "to_team_id": 1,
            },
        ]
    )
    players = pd.DataFrame(
        [
            {"season": 2025, "source_player_id": 10, "full_name": "Player Ten"},
            {"season": 2025, "source_player_id": 20, "full_name": "Player Twenty"},
        ]
    )
    teams = pd.DataFrame(
        [
            {"season": 2025, "source_team_id": 1, "team_name": "Team One"},
            {"season": 2025, "source_team_id": 2, "team_name": "Team Two"},
        ]
    )
    assignments = pd.DataFrame(
        [
            {
                "season": 2025,
                "source_team_id": 1,
                "canonical_manager_id": "manager-a",
                "canonical_display_name": "Manager A",
            },
            {
                "season": 2025,
                "source_team_id": 2,
                "canonical_manager_id": "manager-b",
                "canonical_display_name": "Manager B",
            },
        ]
    )

    history = build_trade_history(trades, items, players, teams, assignments)

    assert history.iloc[0]["managers"] == "Manager A ↔ Manager B"
    assert "Manager A received Player Twenty" in history.iloc[0]["deal"]
    assert "Manager B received Player Ten" in history.iloc[0]["deal"]
    assert len(manager_trade_history(history, "manager-a")) == 1
    assert manager_trade_history(history, "manager-c").empty

"""Deterministic, source-traceable normalization of validated ESPN snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

NORMALIZATION_VERSION = "phase2.v1"

STRING = pa.string()
INT = pa.int64()
FLOAT = pa.float64()
BOOL = pa.bool_()

TABLE_SCHEMAS: dict[str, pa.Schema] = {
    "seasons": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("league_name", STRING),
            ("scoring_type", STRING),
            ("regular_season_periods", INT),
            ("playoff_team_count", INT),
            ("current_scoring_period", INT),
            ("is_active", BOOL),
            ("lineup_slot_counts_json", STRING),
            ("normalization_version", STRING),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "managers": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_member_id", STRING),
            ("display_name", STRING),
            ("is_league_manager", BOOL),
            ("canonical_manager_id", STRING),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "season_teams": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_team_id", INT),
            ("team_name", STRING),
            ("abbreviation", STRING),
            ("location", STRING),
            ("nickname", STRING),
            ("primary_owner_id", STRING),
            ("owner_ids_json", STRING),
            ("division_id", INT),
            ("logo_url", STRING),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "matchups": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_matchup_id", INT),
            ("scoring_period", INT),
            ("matchup_period", INT),
            ("home_team_id", INT),
            ("away_team_id", INT),
            ("home_score", FLOAT),
            ("away_score", FLOAT),
            ("winner", STRING),
            ("playoff_tier", STRING),
            ("is_playoff", BOOL),
            ("is_consolation", BOOL),
            ("is_bye", BOOL),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "team_scores": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_matchup_id", INT),
            ("scoring_period", INT),
            ("source_team_id", INT),
            ("opponent_team_id", INT),
            ("side", STRING),
            ("points", FLOAT),
            ("result", STRING),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "playoff_results": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_matchup_id", INT),
            ("scoring_period", INT),
            ("playoff_tier", STRING),
            ("home_team_id", INT),
            ("away_team_id", INT),
            ("winner", STRING),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "players": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_player_id", INT),
            ("full_name", STRING),
            ("pro_team_id", INT),
            ("default_position_id", INT),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "drafts": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("drafted", BOOL),
            ("in_progress", BOOL),
            ("complete_date_epoch_ms", INT),
            ("pick_count", INT),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "draft_picks": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_pick_id", INT),
            ("overall_pick", INT),
            ("round", INT),
            ("round_pick", INT),
            ("source_team_id", INT),
            ("source_member_id", STRING),
            ("source_player_id", INT),
            ("player_name", STRING),
            ("bid_amount", FLOAT),
            ("is_keeper", BOOL),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "roster_snapshots": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("snapshot_type", STRING),
            ("scoring_period", INT),
            ("source_team_id", INT),
            ("coverage_status", STRING),
            ("entry_count", INT),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
    "roster_players": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("snapshot_type", STRING),
            ("scoring_period", INT),
            ("source_team_id", INT),
            ("source_player_id", INT),
            ("lineup_slot_id", INT),
            ("acquisition_type", STRING),
            ("acquisition_date_epoch_ms", INT),
            ("player_name", STRING),
            ("pro_team_id", INT),
            ("default_position_id", INT),
            ("source_file", STRING),
            ("source_row_key", STRING),
        ]
    ),
}

SORT_KEYS: dict[str, list[str]] = {
    name: [field for field in ("season", "source_row_key") if field in schema.names]
    for name, schema in TABLE_SCHEMAS.items()
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _row_key(*parts: Any) -> str:
    return ":".join("null" if part is None else str(part) for part in parts)


def _player(entry: Mapping[str, Any]) -> dict[str, Any]:
    pool = _dict(entry.get("playerPoolEntry")) or _dict(entry)
    player = _dict(pool.get("player"))
    return player


def normalize_season(
    *, league_id: int, season: int, payloads: Mapping[str, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Normalize one season without canonical identity or analytics decisions."""
    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_SCHEMAS}
    league = payloads["league"]
    settings = _dict(league.get("settings"))
    schedule_settings = _dict(settings.get("scheduleSettings"))
    scoring_settings = _dict(settings.get("scoringSettings"))
    roster_settings = _dict(settings.get("rosterSettings"))
    status = _dict(league.get("status"))
    league_source = f"{season}/league.json"
    tables["seasons"].append(
        {
            "league_id": league_id,
            "season": season,
            "league_name": _string(settings.get("name")) or _string(league.get("name")),
            "scoring_type": _string(scoring_settings.get("scoringType")),
            "regular_season_periods": _int(schedule_settings.get("matchupPeriodCount")),
            "playoff_team_count": _int(schedule_settings.get("playoffTeamCount")),
            "current_scoring_period": _int(status.get("currentScoringPeriod")),
            "is_active": not bool(status.get("isGameOver", False)),
            "lineup_slot_counts_json": _json(roster_settings.get("lineupSlotCounts", {})),
            "normalization_version": NORMALIZATION_VERSION,
            "source_file": league_source,
            "source_row_key": _row_key(season, "league"),
        }
    )

    for index, raw_member in enumerate(_list(league.get("members"))):
        member = _dict(raw_member)
        member_id = _string(member.get("id"))
        tables["managers"].append(
            {
                "league_id": league_id,
                "season": season,
                "source_member_id": member_id,
                "display_name": _string(member.get("displayName")),
                "is_league_manager": bool(member.get("isLeagueManager", False)),
                "canonical_manager_id": None,
                "source_file": league_source,
                "source_row_key": _row_key(season, "member", member_id or index),
            }
        )

    for index, raw_team in enumerate(_list(league.get("teams"))):
        team = _dict(raw_team)
        team_id = _int(team.get("id"))
        owners = [str(item) for item in _list(team.get("owners"))]
        location = _string(team.get("location"))
        nickname = _string(team.get("nickname"))
        tables["season_teams"].append(
            {
                "league_id": league_id,
                "season": season,
                "source_team_id": team_id,
                "team_name": _string(team.get("name"))
                or " ".join(part for part in (location, nickname) if part)
                or None,
                "abbreviation": _string(team.get("abbrev")),
                "location": location,
                "nickname": nickname,
                "primary_owner_id": _string(team.get("primaryOwner")),
                "owner_ids_json": _json(owners),
                "division_id": _int(team.get("divisionId")),
                "logo_url": _string(team.get("logo")),
                "source_file": league_source,
                "source_row_key": _row_key(season, "team", team_id or index),
            }
        )

    schedule = payloads["schedule"]
    schedule_source = f"{season}/matchups.json"
    for index, raw_matchup in enumerate(_list(schedule.get("schedule"))):
        matchup = _dict(raw_matchup)
        matchup_id = _int(matchup.get("id"))
        period = _int(matchup.get("matchupPeriodId"))
        home = _dict(matchup.get("home"))
        away = _dict(matchup.get("away"))
        score_periods = {
            int(raw_period)
            for side_payload in (home, away)
            for raw_period in _dict(side_payload.get("pointsByScoringPeriod"))
            if str(raw_period).isdigit()
        }
        scoring_period = next(iter(score_periods)) if len(score_periods) == 1 else None
        if not score_periods:
            scoring_period = period
        home_id, away_id = _int(home.get("teamId")), _int(away.get("teamId"))
        tier = _string(matchup.get("playoffTierType")) or "NONE"
        winner = _string(matchup.get("winner"))
        is_playoff = tier != "NONE"
        key = _row_key(season, "matchup", matchup_id if matchup_id is not None else index)
        tables["matchups"].append(
            {
                "league_id": league_id,
                "season": season,
                "source_matchup_id": matchup_id,
                "scoring_period": scoring_period,
                "matchup_period": period,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_score": _float(home.get("totalPoints")),
                "away_score": _float(away.get("totalPoints")),
                "winner": winner,
                "playoff_tier": tier,
                "is_playoff": is_playoff,
                "is_consolation": tier == "LOSERS_CONSOLATION_LADDER",
                "is_bye": home_id is None or away_id is None,
                "source_file": schedule_source,
                "source_row_key": key,
            }
        )
        if is_playoff:
            tables["playoff_results"].append(
                {
                    "league_id": league_id,
                    "season": season,
                    "source_matchup_id": matchup_id,
                    "scoring_period": scoring_period,
                    "playoff_tier": tier,
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "winner": winner,
                    "source_file": schedule_source,
                    "source_row_key": key,
                }
            )
        for side, current, opponent in (("home", home, away), ("away", away, home)):
            team_id = _int(current.get("teamId"))
            if team_id is None:
                continue
            result = None
            if winner in {"HOME", "AWAY", "TIE"}:
                result = (
                    "T" if winner == "TIE" else ("W" if winner.upper() == side.upper() else "L")
                )
            points_by_period = _dict(current.get("pointsByScoringPeriod"))
            if points_by_period:
                score_items = sorted(points_by_period.items(), key=lambda item: int(item[0]))
            else:
                score_items = [(str(period), current.get("totalPoints"))]
            score_result = result if len(score_items) == 1 else None
            for score_period, points in score_items:
                score_period_int = int(score_period) if str(score_period).isdigit() else period
                tables["team_scores"].append(
                    {
                        "league_id": league_id,
                        "season": season,
                        "source_matchup_id": matchup_id,
                        "scoring_period": score_period_int,
                        "source_team_id": team_id,
                        "opponent_team_id": _int(opponent.get("teamId")),
                        "side": side,
                        "points": _float(points),
                        "result": score_result,
                        "source_file": schedule_source,
                        "source_row_key": _row_key(key, side, score_period_int),
                    }
                )

    draft_payload = payloads["draft"]
    draft = _dict(draft_payload.get("draftDetail"))
    picks = _list(draft.get("picks"))
    draft_source = f"{season}/draft.json"
    tables["drafts"].append(
        {
            "league_id": league_id,
            "season": season,
            "drafted": bool(draft.get("drafted")),
            "in_progress": bool(draft.get("inProgress")),
            "complete_date_epoch_ms": _int(draft.get("completeDate")),
            "pick_count": len(picks),
            "source_file": draft_source,
            "source_row_key": _row_key(season, "draft"),
        }
    )
    player_rows: dict[int, dict[str, Any]] = {}
    for index, raw_pick in enumerate(picks):
        pick = _dict(raw_pick)
        player_id = _int(pick.get("playerId"))
        overall = _int(pick.get("overallPickNumber"))
        pick_id = _int(pick.get("id"))
        tables["draft_picks"].append(
            {
                "league_id": league_id,
                "season": season,
                "source_pick_id": pick_id,
                "overall_pick": overall,
                "round": _int(pick.get("roundId")),
                "round_pick": _int(pick.get("roundPickNumber")),
                "source_team_id": _int(pick.get("teamId")),
                "source_member_id": _string(pick.get("memberId")),
                "source_player_id": player_id,
                "player_name": _string(pick.get("playerName")),
                "bid_amount": _float(pick.get("bidAmount")),
                "is_keeper": bool(pick.get("keeper", False)),
                "source_file": draft_source,
                "source_row_key": _row_key(season, "pick", overall or pick_id or index),
            }
        )
        if player_id is not None:
            player_rows.setdefault(
                player_id,
                {
                    "league_id": league_id,
                    "season": season,
                    "source_player_id": player_id,
                    "full_name": _string(pick.get("playerName")),
                    "pro_team_id": None,
                    "default_position_id": None,
                    "source_file": draft_source,
                    "source_row_key": _row_key(season, "player", player_id),
                },
            )

    def add_rosters(
        payload: dict[str, Any], snapshot_type: str, scoring_period: int | None
    ) -> None:
        source = (
            f"{season}/rosters.json"
            if snapshot_type == "season_roster"
            else f"{season}/lineups/week_{scoring_period:02d}.json"
        )
        if snapshot_type == "season_roster":
            sides = [
                (_int(team.get("id")), _dict(team.get("roster")))
                for team in map(_dict, _list(payload.get("teams")))
            ]
        else:
            sides = []
            for raw_matchup in _list(payload.get("schedule")):
                matchup = _dict(raw_matchup)
                for side_name in ("home", "away"):
                    side = _dict(matchup.get(side_name))
                    if "rosterForCurrentScoringPeriod" in side:
                        sides.append(
                            (
                                _int(side.get("teamId")),
                                _dict(side.get("rosterForCurrentScoringPeriod")),
                            )
                        )
        seen: set[int] = set()
        for team_id, roster in sides:
            if team_id is None or team_id in seen:
                continue
            seen.add(team_id)
            entries = _list(roster.get("entries"))
            snapshot_key = _row_key(season, snapshot_type, scoring_period, team_id)
            tables["roster_snapshots"].append(
                {
                    "league_id": league_id,
                    "season": season,
                    "snapshot_type": snapshot_type,
                    "scoring_period": scoring_period,
                    "source_team_id": team_id,
                    "coverage_status": "available-empty" if not entries else "complete",
                    "entry_count": len(entries),
                    "source_file": source,
                    "source_row_key": snapshot_key,
                }
            )
            for entry_index, raw_entry in enumerate(entries):
                entry = _dict(raw_entry)
                pool = _dict(entry.get("playerPoolEntry"))
                player = _player(entry)
                player_id = _int(player.get("id")) or _int(pool.get("id"))
                tables["roster_players"].append(
                    {
                        "league_id": league_id,
                        "season": season,
                        "snapshot_type": snapshot_type,
                        "scoring_period": scoring_period,
                        "source_team_id": team_id,
                        "source_player_id": player_id,
                        "lineup_slot_id": _int(entry.get("lineupSlotId")),
                        "acquisition_type": _string(pool.get("acquisitionType")),
                        "acquisition_date_epoch_ms": _int(pool.get("acquisitionDate")),
                        "player_name": _string(player.get("fullName")),
                        "pro_team_id": _int(player.get("proTeamId")),
                        "default_position_id": _int(player.get("defaultPositionId")),
                        "source_file": source,
                        "source_row_key": _row_key(snapshot_key, player_id or entry_index),
                    }
                )
                if player_id is not None:
                    player_rows[player_id] = {
                        "league_id": league_id,
                        "season": season,
                        "source_player_id": player_id,
                        "full_name": _string(player.get("fullName")),
                        "pro_team_id": _int(player.get("proTeamId")),
                        "default_position_id": _int(player.get("defaultPositionId")),
                        "source_file": source,
                        "source_row_key": _row_key(season, "player", player_id),
                    }

    add_rosters(payloads["rosters"], "season_roster", None)
    for key in sorted(payloads):
        if key.startswith("lineups_"):
            add_rosters(payloads[key], "weekly_lineup", int(key.removeprefix("lineups_")))
    tables["players"].extend(player_rows.values())
    return tables


def combine_tables(
    season_tables: Iterable[Mapping[str, list[dict[str, Any]]]],
) -> dict[str, pd.DataFrame]:
    """Combine seasons into stable table frames with contract columns."""
    combined: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_SCHEMAS}
    for tables in season_tables:
        for name in combined:
            combined[name].extend(tables.get(name, []))
    frames: dict[str, pd.DataFrame] = {}
    for name, rows in combined.items():
        columns = TABLE_SCHEMAS[name].names
        frame = pd.DataFrame(rows, columns=columns)
        if not frame.empty:
            frame = frame.sort_values(SORT_KEYS[name], kind="stable", na_position="last")
            if frame["source_row_key"].duplicated().any():
                raise ValueError(f"Duplicate source_row_key values in {name}.")
        frames[name] = frame.reset_index(drop=True)
    return frames


def write_parquet_tables(frames: Mapping[str, pd.DataFrame], output_root: Path) -> None:
    """Write deterministic table contracts to a staging directory."""
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".gitkeep").write_text("\n", encoding="utf-8")
    for name, schema in TABLE_SCHEMAS.items():
        frame = frames[name]
        table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=False)
        pq.write_table(table, output_root / f"{name}.parquet", compression="zstd")

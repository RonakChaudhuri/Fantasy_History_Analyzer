#!/usr/bin/env python3
"""Run the credentialed, share-safe ESPN feasibility audit for Phase 0.

The script never writes an ESPN response body. It records structural field paths,
aggregate counts, and the scoring/lineup settings needed for the audit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_TEMPLATE = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}"
)
HISTORY_API_TEMPLATE = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory/{league_id}"
)
RECEPTION_STAT_ID = 53
SECRET_NAMES = ("ESPN_S2", "ESPN_SWID")
SECTIONS: dict[str, tuple[str, ...]] = {
    "league": ("mSettings", "mTeam", "mNav"),
    "schedule": ("mMatchup", "mMatchupScore"),
    "draft": ("mDraftDetail",),
    "rosters": ("mRoster",),
    "lineups": ("mMatchupScore", "mScoreboard"),
}
SECTION_PARAMS: dict[str, dict[str, int]] = {"lineups": {"scoringPeriodId": 1}}


class AuditError(RuntimeError):
    """A user-actionable audit failure with no response body or secrets."""


class SeasonUnavailableError(AuditError):
    """The requested league season does not exist or cannot be queried."""


@dataclass(frozen=True)
class Config:
    league_id: int
    first_season: int
    espn_s2: str
    espn_swid: str

    @classmethod
    def from_environment(cls) -> "Config":
        missing = [name for name in SECRET_NAMES if not os.environ.get(name, "").strip()]
        if missing:
            joined = ", ".join(missing)
            raise AuditError(
                f"Missing {joined}. Add them to the local .env file; never paste them into chat."
            )
        try:
            league_id = int(os.environ.get("ESPN_LEAGUE_ID", "78212237"))
            first_season = int(os.environ.get("ESPN_FIRST_SEASON", "2019"))
        except ValueError as exc:
            raise AuditError("ESPN_LEAGUE_ID and ESPN_FIRST_SEASON must be integers.") from exc
        return cls(
            league_id=league_id,
            first_season=first_season,
            espn_s2=os.environ["ESPN_S2"].strip(),
            espn_swid=os.environ["ESPN_SWID"].strip(),
        )


def load_env(path: Path) -> None:
    """Load a small KEY=VALUE .env file without adding a Phase 1 dependency."""
    if not path.exists():
        return
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AuditError(f"Invalid .env entry on line {number}.")
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise AuditError(f"Invalid .env variable name on line {number}.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _request_json(config: Config, season: int, url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Cookie": f"espn_s2={config.espn_s2}; SWID={config.espn_swid}",
            "User-Agent": "fantasy-history-analyzer-phase0/1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
            payload = json.load(response)
    except HTTPError:
        raise
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", "network timeout")
        raise AuditError(f"ESPN could not be reached for season {season}: {reason!s}") from None
    except json.JSONDecodeError:
        # ESPN can return an HTML landing page for a league season that has not
        # been created yet. During discovery this is an unavailable candidate;
        # a specifically requested representative season still fails the audit.
        raise SeasonUnavailableError(
            f"League season {season} returned no usable JSON response."
        ) from None
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        payload = payload[0]
    if not isinstance(payload, dict):
        raise AuditError(f"ESPN returned an unexpected top-level shape for season {season}.")
    return payload


def fetch_json(
    config: Config,
    season: int,
    views: Iterable[str],
    extra_params: Mapping[str, int | str] | None = None,
) -> dict[str, Any]:
    parameters: list[tuple[str, int | str]] = [("view", view) for view in views]
    parameters.extend((extra_params or {}).items())
    query = urlencode(parameters)
    url = API_TEMPLATE.format(season=season, league_id=config.league_id) + "?" + query
    try:
        return _request_json(config, season, url)
    except HTTPError as exc:
        if exc.code not in (401, 403):
            if exc.code in (400, 404):
                raise SeasonUnavailableError(
                    f"League season {season} is unavailable (HTTP {exc.code})."
                ) from None
            raise AuditError(
                f"ESPN request failed for season {season} (HTTP {exc.code})."
            ) from None

    history_query = urlencode([("seasonId", season), *parameters])
    history_url = HISTORY_API_TEMPLATE.format(league_id=config.league_id) + "?" + history_query
    try:
        return _request_json(config, season, history_url)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise AuditError(
                f"ESPN rejected access for season {season} (HTTP {exc.code}); refresh local credentials."
            ) from None
        if exc.code in (400, 404):
            raise SeasonUnavailableError(
                f"League season {season} is unavailable (HTTP {exc.code})."
            ) from None
        raise AuditError(f"ESPN request failed for season {season} (HTTP {exc.code}).") from None


def shape_paths(value: Any, prefix: str = "$", output: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    """Describe JSON structure without retaining any scalar response values."""
    output = output if output is not None else {}
    if isinstance(value, Mapping):
        output.setdefault(prefix, set()).add("object")
        for key, child in value.items():
            # Numeric IDs and timestamp-keyed maps contain data keys, not schema
            # fields. Collapsing them keeps cross-season differences meaningful.
            normalized_key = "{key}" if re.fullmatch(r"\d+|\d{4}-\d{2}-\d{2}T.+", str(key)) else key
            shape_paths(child, f"{prefix}.{normalized_key}", output)
    elif isinstance(value, list):
        output.setdefault(prefix, set()).add("array")
        for child in value:
            shape_paths(child, f"{prefix}[]", output)
    elif value is None:
        output.setdefault(prefix, set()).add("null")
    elif isinstance(value, bool):
        output.setdefault(prefix, set()).add("boolean")
    elif isinstance(value, (int, float)):
        output.setdefault(prefix, set()).add("number")
    else:
        output.setdefault(prefix, set()).add("string")
    return output


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(contains_key(child, key) for child in value)
    return False


def availability(present: bool, count: int | None = None) -> str:
    if not present:
        return "unavailable"
    if count == 0:
        return "available-empty"
    return "available"


def summarize(payloads: Mapping[str, dict[str, Any]], season: int) -> dict[str, Any]:
    league = payloads["league"]
    schedule_payload = payloads["schedule"]
    draft_payload = payloads["draft"]
    roster_payload = payloads["rosters"]
    lineup_payload = payloads["lineups"]
    settings = _dict(league.get("settings"))
    scoring = _dict(settings.get("scoringSettings"))
    roster_settings = _dict(settings.get("rosterSettings"))
    schedule = _list(schedule_payload.get("schedule"))
    lineup_schedule = _list(lineup_payload.get("schedule"))
    teams = _list(league.get("teams"))
    roster_teams = _list(roster_payload.get("teams"))
    scoring_items = _list(scoring.get("scoringItems"))
    reception_items = [
        item for item in scoring_items
        if isinstance(item, dict) and item.get("statId") == RECEPTION_STAT_ID
    ]
    lineup_counts = roster_settings.get("lineupSlotCounts")
    draft = _dict(draft_payload.get("draftDetail"))
    picks = _list(draft.get("picks"))

    playoff_games = 0
    lineup_entries = 0
    for matchup in schedule:
        if not isinstance(matchup, dict):
            continue
        if matchup.get("playoffTierType") not in (None, "NONE"):
            playoff_games += 1
    for matchup in lineup_schedule:
        if not isinstance(matchup, dict):
            continue
        for side in ("home", "away"):
            team = _dict(matchup.get(side))
            roster = _dict(team.get("rosterForCurrentScoringPeriod"))
            lineup_entries += len(_list(roster.get("entries")))

    roster_entries = 0
    for team in roster_teams:
        roster_entries += len(_list(_dict(_dict(team).get("roster")).get("entries")))

    reception_points = [item.get("points") for item in reception_items]
    coverage = {
        "settings": bool(settings),
        "members": len(_list(league.get("members"))),
        "teams": len(teams),
        "schedule_matchups": len(schedule),
        "playoff_matchups": playoff_games,
        "draft_picks": len(picks),
        "lineup_entries": lineup_entries,
        "roster_entries": roster_entries,
    }
    return {
        "season": season,
        "coverage": coverage,
        "availability": {
            "settings": availability("settings" in league),
            "members": availability("members" in league, coverage["members"]),
            "teams": availability("teams" in league, coverage["teams"]),
            "schedule": availability("schedule" in schedule_payload, coverage["schedule_matchups"]),
            "playoffs": availability(
                contains_key(schedule, "playoffTierType"), coverage["playoff_matchups"]
            ),
            "drafts": availability(contains_key(draft_payload, "picks"), coverage["draft_picks"]),
            "lineups": availability(
                contains_key(lineup_payload, "rosterForCurrentScoringPeriod"),
                coverage["lineup_entries"],
            ),
            "rosters": availability(contains_key(roster_payload, "roster"), coverage["roster_entries"]),
        },
        "settings": {
            "scoring_type": scoring.get("scoringType"),
            "reception_stat_id": RECEPTION_STAT_ID,
            "reception_points": reception_points,
            "is_ppr": 1 in reception_points or 1.0 in reception_points,
            "lineup_slot_counts": lineup_counts if isinstance(lineup_counts, dict) else None,
        },
    }


def representative_seasons(first: int, latest: int) -> list[int]:
    if latest < first:
        raise AuditError(f"Latest season {latest} precedes first season {first}.")
    return sorted({first, (first + latest) // 2, latest})


def has_league(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("settings")) and bool(payload.get("teams"))


def discover_latest(config: Config, requested: int | None) -> tuple[int, dict[str, Any] | None]:
    if requested is not None:
        return requested, None
    current_year = datetime.now(UTC).year
    for season in range(current_year, config.first_season - 1, -1):
        try:
            payload = fetch_json(config, season, SECTIONS["league"])
        except SeasonUnavailableError:
            continue
        if has_league(payload):
            return season, payload
    raise AuditError("No accessible league season was found from the first season through this year.")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def markdown_report(result: Mapping[str, Any]) -> str:
    seasons = _list(result.get("seasons"))
    lines = [
        "# Phase 0 ESPN feasibility audit",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "Only aggregate counts, selected league settings, and JSON field types are saved. ",
        "No response scalar values, member details, cookies, or request headers are retained.",
        "",
        "## Coverage matrix",
        "",
        "| Season | Settings | Members | Teams | Schedule | Playoffs | Draft picks | Lineups | Rosters | PPR |",
        "| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for item in seasons:
        coverage = item["coverage"]
        settings = item["settings"]
        available = item["availability"]

        def cell(area: str, count: int) -> str:
            return "unavailable" if available[area] == "unavailable" else str(count)

        lines.append(
            f"| {item['season']} | {'yes' if coverage['settings'] else 'unavailable'} | "
            f"{cell('members', coverage['members'])} | {cell('teams', coverage['teams'])} | "
            f"{cell('schedule', coverage['schedule_matchups'])} | "
            f"{cell('playoffs', coverage['playoff_matchups'])} | "
            f"{cell('drafts', coverage['draft_picks'])} | "
            f"{cell('lineups', coverage['lineup_entries'])} | "
            f"{cell('rosters', coverage['roster_entries'])} | "
            f"{'yes' if settings['is_ppr'] else 'no/unknown'} |"
        )
    lines.extend(["", "## Response-shape differences", ""])
    differences = _list(result.get("shape_differences"))
    if differences:
        lines.extend(f"- `{item}`" for item in differences)
    else:
        lines.append("- No field-path differences detected in the representative samples.")
    lines.extend(["", "## Lineup settings", ""])
    for item in seasons:
        lines.append(
            f"- {item['season']}: `{json.dumps(item['settings']['lineup_slot_counts'], sort_keys=True)}`"
        )
    lines.append("")
    return "\n".join(lines)


def run(config: Config, output_root: Path, latest_override: int | None) -> Path:
    latest, discovered_payload = discover_latest(config, latest_override)
    seasons = representative_seasons(config.first_season, latest)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_root = output_root / "runs" / timestamp
    summaries: list[dict[str, Any]] = []
    all_paths: dict[int, set[str]] = {}

    for season in seasons:
        payloads: dict[str, dict[str, Any]] = {}
        season_paths: set[str] = set()
        for section, views in SECTIONS.items():
            if section == "league" and season == latest and discovered_payload is not None:
                payload = discovered_payload
            else:
                payload = fetch_json(config, season, views, SECTION_PARAMS.get(section))
            payloads[section] = payload
            shape = shape_paths(payload)
            serialized_shape = {path: sorted(types) for path, types in sorted(shape.items())}
            atomic_json(run_root / str(season) / f"{section}.shape.json", serialized_shape)
            season_paths.update(f"{section}:{path}" for path in shape)
        summaries.append(summarize(payloads, season))
        all_paths[season] = season_paths

    baseline = all_paths[seasons[0]]
    differences: list[str] = []
    for season in seasons[1:]:
        for path in sorted(all_paths[season] - baseline):
            differences.append(f"{season} adds {path}")
        for path in sorted(baseline - all_paths[season]):
            differences.append(f"{season} lacks {path}")

    result = {
        "audit_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "league_id": config.league_id,
        "representative_seasons": seasons,
        "seasons": summaries,
        "shape_differences": differences,
    }
    atomic_json(run_root / "audit.json", result)
    report_path = run_root / "report.md"
    report_path.write_text(markdown_report(result), encoding="utf-8")
    atomic_json(output_root / "latest.json", {"run": str(run_root.relative_to(output_root))})
    return report_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--latest-season", type=int, help="Skip latest-season discovery.")
    parser.add_argument("--output", type=Path, default=Path("data/audit/phase0"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        load_env(args.env_file)
        config = Config.from_environment()
        report_path = run(config, args.output, args.latest_season)
    except AuditError as exc:
        print(f"Phase 0 audit stopped: {exc}", file=sys.stderr)
        return 2
    print(f"Phase 0 audit complete: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

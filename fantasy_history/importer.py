"""Transactional ESPN snapshot importing and offline Parquet rebuilding."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_history.config import Settings
from fantasy_history.espn_client import EspnClient
from fantasy_history.normalization import combine_tables, normalize_season, write_parquet_tables
from fantasy_history.validation import (
    CoverageRecord,
    SnapshotManifest,
    collection_coverage,
    validate_league_identity,
    validate_section,
)

IMPORTER_VERSION = "phase2.v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "data" / ".staging"

SECTION_VIEWS: dict[str, tuple[str, ...]] = {
    "league": ("mSettings", "mTeam", "mNav"),
    "schedule": ("mMatchup", "mMatchupScore"),
    "draft": ("mDraftDetail",),
    "rosters": ("mRoster",),
}

PRIVATE_MEMBER_KEYS = {
    "email",
    "phone",
    "notificationSettings",
    "notificationPreferences",
}


class ImportPipelineError(RuntimeError):
    """A safe import or integrity failure."""


def _sanitize_snapshot(value: Any) -> Any:
    """Drop unnecessary private member contact/notification fields before persistence."""
    if isinstance(value, dict):
        return {
            key: _sanitize_snapshot(child)
            for key, child in value.items()
            if key not in PRIVATE_MEMBER_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_snapshot(child) for child in value]
    return value


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _shape_paths(value: Any, prefix: str = "$") -> set[str]:
    """Record structure without retaining any response scalar values."""
    paths: set[str] = set()
    if isinstance(value, dict):
        paths.add(f"{prefix}:object")
        for key, child in value.items():
            normalized = "{key}" if re.fullmatch(r"\d+|\d{4}-\d{2}-\d{2}T.+", str(key)) else key
            paths.update(_shape_paths(child, f"{prefix}.{normalized}"))
    elif isinstance(value, list):
        paths.add(f"{prefix}:array")
        for child in value:
            paths.update(_shape_paths(child, f"{prefix}[]"))
    elif value is None:
        paths.add(f"{prefix}:null")
    elif isinstance(value, bool):
        paths.add(f"{prefix}:boolean")
    elif isinstance(value, (int, float)):
        paths.add(f"{prefix}:number")
    else:
        paths.add(f"{prefix}:string")
    return paths


def _write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _canonical_json(value)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return hashlib.sha256(content).hexdigest()


def _section_path(root: Path, section: str) -> Path:
    if section.startswith("lineups_"):
        week = int(section.removeprefix("lineups_"))
        return root / "lineups" / f"week_{week:02d}.json"
    names = {"schedule": "matchups.json"}
    return root / names.get(section, f"{section}.json")


def _count_section(section: str, payload: Mapping[str, Any]) -> int:
    if section == "league":
        return len(payload.get("teams", [])) if isinstance(payload.get("teams"), list) else 0
    if section in {"schedule", "lineups"}:
        return len(payload.get("schedule", [])) if isinstance(payload.get("schedule"), list) else 0
    if section == "draft":
        detail = payload.get("draftDetail")
        return len(detail.get("picks", [])) if isinstance(detail, dict) else 0
    if section == "rosters":
        count = 0
        for team in payload.get("teams", []) if isinstance(payload.get("teams"), list) else []:
            roster = team.get("roster") if isinstance(team, dict) else None
            count += len(roster.get("entries", [])) if isinstance(roster, dict) else 0
        return count
    return 0


def _has_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(_has_key(child, target) for child in value.values())
    if isinstance(value, list):
        return any(_has_key(child, target) for child in value)
    return False


def _coverage(payloads: Mapping[str, dict[str, Any]], *, active: bool) -> dict[str, CoverageRecord]:
    league = payloads["league"]
    schedule = payloads["schedule"]
    draft = payloads["draft"]
    rosters = payloads["rosters"]
    lineup_payloads = [value for key, value in payloads.items() if key.startswith("lineups_")]
    lineup_entries = 0
    for payload in lineup_payloads:
        for matchup in payload.get("schedule", []):
            if not isinstance(matchup, dict):
                continue
            for side_name in ("home", "away"):
                side = matchup.get(side_name)
                roster = (
                    side.get("rosterForCurrentScoringPeriod") if isinstance(side, dict) else None
                )
                if isinstance(roster, dict):
                    lineup_entries += len(roster.get("entries", []))
    playoff_count = sum(
        1
        for matchup in schedule.get("schedule", [])
        if isinstance(matchup, dict) and matchup.get("playoffTierType") not in (None, "NONE")
    )
    return {
        "settings": collection_coverage(present="settings" in league, count=1),
        "members": collection_coverage(
            present="members" in league,
            count=len(league.get("members", []))
            if isinstance(league.get("members"), list)
            else None,
        ),
        "teams": collection_coverage(
            present="teams" in league, count=_count_section("league", league)
        ),
        "schedule": collection_coverage(
            present="schedule" in schedule,
            count=_count_section("schedule", schedule),
            partial=active,
        ),
        "playoffs": collection_coverage(
            present=_has_key(schedule.get("schedule", []), "playoffTierType"),
            count=playoff_count,
            partial=active,
        ),
        "drafts": collection_coverage(
            present=_has_key(draft.get("draftDetail", {}), "picks"),
            count=_count_section("draft", draft),
            partial=active,
        ),
        "rosters": collection_coverage(
            present=_has_key(rosters.get("teams", []), "roster"),
            count=_count_section("rosters", rosters),
            partial=active,
        ),
        "lineups": collection_coverage(
            present=any(
                _has_key(payload, "rosterForCurrentScoringPeriod") for payload in lineup_payloads
            ),
            count=lineup_entries,
            partial=active,
        ),
    }


def fetch_season(client: EspnClient, season: int) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Fetch and validate every supported section for one season."""
    payloads: dict[str, dict[str, Any]] = {}
    routes: list[str] = []
    for section, views in SECTION_VIEWS.items():
        payload, route = client.fetch(season, views)
        payloads[section] = validate_section(section, payload, season=season)
        routes.append(route)
    validate_league_identity(payloads["league"], league_id=client.settings.league_id, season=season)

    schedule_periods = sorted(
        {
            int(matchup["matchupPeriodId"])
            for matchup in payloads["schedule"].get("schedule", [])
            if isinstance(matchup, dict) and isinstance(matchup.get("matchupPeriodId"), int)
        }
    )
    for period in schedule_periods:
        section = f"lineups_{period}"
        payload, route = client.fetch(
            season,
            ("mMatchupScore", "mScoreboard"),
            {"scoringPeriodId": period},
        )
        payloads[section] = validate_section(section, payload, season=season)
        routes.append(route)
    return payloads, routes


def stage_season_snapshot(
    *,
    league_id: int,
    season: int,
    payloads: Mapping[str, dict[str, Any]],
    routes: Sequence[str],
    destination: Path,
    fetched_at: datetime | None = None,
) -> SnapshotManifest:
    """Write a fully validated season snapshot and manifest into staging."""
    destination.mkdir(parents=True, exist_ok=False)
    fetch_time = fetched_at or datetime.now(UTC)
    validate_league_identity(payloads["league"], league_id=league_id, season=season)
    checksums: dict[str, str] = {}
    source_shapes: dict[str, list[str]] = {}
    row_counts: dict[str, int] = {}
    sanitized_payloads: dict[str, dict[str, Any]] = {}
    for section, payload in payloads.items():
        sanitized = _sanitize_snapshot(payload)
        if not isinstance(sanitized, dict):
            raise ImportPipelineError(f"Season {season} {section} could not be sanitized.")
        sanitized_payloads[section] = sanitized
        path = _section_path(destination, section)
        relative = path.relative_to(destination).as_posix()
        checksums[relative] = _write_json(path, sanitized)
        source_shapes[relative] = sorted(_shape_paths(sanitized))
        row_counts[section] = _count_section(
            "lineups" if section.startswith("lineups_") else section, sanitized
        )
    status = _dict(sanitized_payloads["league"].get("status"))
    active = season >= fetch_time.year and not bool(status.get("isGameOver", False))
    route = routes[0] if routes and len(set(routes)) == 1 else "mixed"
    warnings: list[str] = []
    if any(key in json.dumps(payloads) for key in PRIVATE_MEMBER_KEYS):
        warnings.append("Unnecessary member contact or notification fields were removed.")
    manifest = SnapshotManifest(
        importer_version=IMPORTER_VERSION,
        league_id=league_id,
        season=season,
        fetched_at=fetch_time.isoformat(),
        route=route,
        source_checksums=checksums,
        source_shapes=source_shapes,
        coverage=_coverage(sanitized_payloads, active=active),
        row_counts=row_counts,
        warnings=warnings,
    )
    _write_json(destination / "manifest.json", manifest.model_dump(mode="json"))
    return manifest


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_season_snapshot(path: Path) -> tuple[SnapshotManifest, dict[str, dict[str, Any]]]:
    """Load a snapshot only after validating its manifest and checksums."""
    try:
        manifest = SnapshotManifest.model_validate_json((path / "manifest.json").read_text())
    except (OSError, ValueError) as exc:
        raise ImportPipelineError(f"Invalid or missing manifest for snapshot {path.name}.") from exc
    payloads: dict[str, dict[str, Any]] = {}
    for relative, expected in manifest.source_checksums.items():
        source = path / relative
        try:
            content = source.read_bytes()
            raw = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportPipelineError(
                f"Snapshot {manifest.season} has an unreadable source file."
            ) from exc
        if hashlib.sha256(content).hexdigest() != expected:
            raise ImportPipelineError(f"Snapshot {manifest.season} failed its checksum check.")
        section = (
            f"lineups_{int(source.stem.removeprefix('week_'))}"
            if source.parent.name == "lineups"
            else ("schedule" if source.name == "matchups.json" else source.stem)
        )
        payloads[section] = validate_section(section, raw, season=manifest.season)
    validate_league_identity(
        payloads["league"], league_id=manifest.league_id, season=manifest.season
    )
    return manifest, payloads


def validate_frames(frames: Mapping[str, pd.DataFrame]) -> list[str]:
    """Run Phase 2 source-row and referential integrity checks."""
    errors: list[str] = []
    for name, frame in frames.items():
        if frame["source_row_key"].isna().any() or frame["source_row_key"].duplicated().any():
            errors.append(f"{name} has missing or duplicate source row keys")
        if frame["season"].isna().any() or frame["source_file"].isna().any():
            errors.append(f"{name} has rows without season/source traceability")
    teams = frames["season_teams"]
    team_keys = set(zip(teams["season"], teams["source_team_id"], strict=False))
    fantasy_team_columns = {
        "home_team_id",
        "away_team_id",
        "source_team_id",
        "opponent_team_id",
    }
    for name in (
        "matchups",
        "team_scores",
        "draft_picks",
        "roster_snapshots",
        "roster_players",
    ):
        frame = frames[name]
        candidate_columns = [column for column in frame if column in fantasy_team_columns]
        for column in candidate_columns:
            for season, team_id in zip(frame["season"], frame[column], strict=False):
                if pd.notna(team_id) and (season, team_id) not in team_keys:
                    errors.append(f"{name}.{column} references an unknown season team")
                    break
    return errors


def _snapshot_dirs(raw_root: Path) -> list[Path]:
    return (
        sorted(
            (path for path in raw_root.iterdir() if path.is_dir() and path.name.isdigit()),
            key=lambda path: int(path.name),
        )
        if raw_root.exists()
        else []
    )


def build_processed(snapshot_dirs: Sequence[Path], *, output_root: Path) -> dict[str, pd.DataFrame]:
    """Rebuild processed tables exclusively from validated raw snapshots."""
    normalized = []
    for snapshot_dir in snapshot_dirs:
        manifest, payloads = load_season_snapshot(snapshot_dir)
        normalized.append(
            normalize_season(
                league_id=manifest.league_id, season=manifest.season, payloads=payloads
            )
        )
    frames = combine_tables(normalized)
    errors = validate_frames(frames)
    if errors:
        raise ImportPipelineError("Processed integrity failed: " + "; ".join(errors))
    write_parquet_tables(frames, output_root)
    return frames


def _promote(
    *,
    staged_seasons: Mapping[int, Path],
    staged_processed: Path,
    raw_root: Path,
    processed_root: Path,
    transaction_root: Path,
) -> None:
    backups = transaction_root / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    touched_seasons: list[int] = []
    processed_backed_up = False
    try:
        raw_root.mkdir(parents=True, exist_ok=True)
        for season, staged in sorted(staged_seasons.items()):
            target = raw_root / str(season)
            backup = backups / f"raw-{season}"
            touched_seasons.append(season)
            if target.exists():
                target.replace(backup)
            staged.replace(target)
        if processed_root.exists():
            processed_root.replace(backups / "processed")
            processed_backed_up = True
        staged_processed.replace(processed_root)
    except Exception:
        if processed_root.exists():
            shutil.rmtree(processed_root)
        if processed_backed_up and (backups / "processed").exists():
            (backups / "processed").replace(processed_root)
        for season in reversed(touched_seasons):
            target = raw_root / str(season)
            if target.exists():
                shutil.rmtree(target)
            backup = backups / f"raw-{season}"
            if backup.exists():
                backup.replace(target)
        raise


def import_seasons(
    settings: Settings,
    seasons: Sequence[int],
    *,
    client: EspnClient | None = None,
    raw_root: Path = DEFAULT_RAW_ROOT,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> dict[str, pd.DataFrame]:
    """Fetch, validate, normalize, and transactionally promote requested seasons."""
    unique_seasons = sorted(set(seasons))
    if not unique_seasons:
        raise ImportPipelineError("At least one season is required.")
    transaction_root = staging_root / uuid.uuid4().hex
    transaction_root.mkdir(parents=True, exist_ok=False)
    owned_client = client is None
    http = client or EspnClient(settings)
    try:
        staged_seasons: dict[int, Path] = {}
        for season in unique_seasons:
            payloads, routes = fetch_season(http, season)
            destination = transaction_root / "raw" / str(season)
            stage_season_snapshot(
                league_id=settings.league_id,
                season=season,
                payloads=payloads,
                routes=routes,
                destination=destination,
            )
            staged_seasons[season] = destination
        snapshot_dirs = [
            staged_seasons.get(int(path.name), path)
            for path in _snapshot_dirs(raw_root)
            if int(path.name) not in staged_seasons
        ] + list(staged_seasons.values())
        snapshot_dirs.sort(key=lambda path: int(path.name))
        processed_stage = transaction_root / "processed"
        frames = build_processed(snapshot_dirs, output_root=processed_stage)
        _promote(
            staged_seasons=staged_seasons,
            staged_processed=processed_stage,
            raw_root=raw_root,
            processed_root=processed_root,
            transaction_root=transaction_root,
        )
        return frames
    finally:
        if owned_client:
            http.close()
        shutil.rmtree(transaction_root, ignore_errors=True)


def rebuild_processed(
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> dict[str, pd.DataFrame]:
    """Atomically reproduce processed files without contacting ESPN."""
    transaction_root = staging_root / uuid.uuid4().hex
    stage = transaction_root / "processed"
    transaction_root.mkdir(parents=True, exist_ok=False)
    try:
        frames = build_processed(_snapshot_dirs(raw_root), output_root=stage)
        backup = transaction_root / "processed-backup"
        try:
            if processed_root.exists():
                processed_root.replace(backup)
            stage.replace(processed_root)
        except Exception:
            if processed_root.exists():
                shutil.rmtree(processed_root)
            if backup.exists():
                backup.replace(processed_root)
            raise
        return frames
    finally:
        shutil.rmtree(transaction_root, ignore_errors=True)

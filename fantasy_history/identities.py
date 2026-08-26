"""Canonical manager mapping, suggestions, and source-traceable resolution."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from fantasy_history.validation import IdentityValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "data" / "config" / "managers.yaml"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
DEFAULT_DERIVED_ROOT = PROJECT_ROOT / "data" / "derived" / "identities"
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "data" / ".staging"
IDENTITY_SCHEMA_VERSION = "phase3.v1"

STRING = pa.string()
INT = pa.int64()

IDENTITY_TABLE_SCHEMAS: dict[str, pa.Schema] = {
    "canonical_managers": pa.schema(
        [
            ("canonical_manager_id", STRING),
            ("display_name", STRING),
            ("aliases_json", STRING),
            ("espn_member_ids_json", STRING),
            ("identity_schema_version", STRING),
        ]
    ),
    "manager_team_assignments": pa.schema(
        [
            ("league_id", INT),
            ("season", INT),
            ("source_team_id", INT),
            ("source_team_row_key", STRING),
            ("source_file", STRING),
            ("primary_owner_id", STRING),
            ("source_member_ids_json", STRING),
            ("canonical_manager_id", STRING),
            ("canonical_display_name", STRING),
            ("resolution_type", STRING),
            ("identity_schema_version", STRING),
        ]
    ),
}


class AssignmentType(StrEnum):
    """Supported attribution modes for one season-specific team."""

    SINGLE_OWNER = "single_owner"
    CO_OWNER = "co_owner"
    OWNERSHIP_TRANSFER = "ownership_transfer"


class ExplicitAssignment(BaseModel):
    """An explicit non-single-owner attribution for a season team."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    season: int = Field(ge=2000, le=2100)
    source_team_id: int = Field(gt=0)
    assignment_type: AssignmentType

    @model_validator(mode="after")
    def reject_single_owner(self) -> ExplicitAssignment:
        if self.assignment_type == AssignmentType.SINGLE_OWNER:
            raise ValueError("Use season_team_ids for single-owner assignments.")
        return self


class CanonicalManager(BaseModel):
    """One deliberately maintained real-manager identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1)
    espn_member_ids: list[str] = Field(default_factory=list)
    season_team_ids: dict[int, int] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    explicit_assignments: list[ExplicitAssignment] = Field(default_factory=list)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned

    @field_validator("espn_member_ids", "aliases")
    @classmethod
    def clean_unique_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("identity lists cannot contain blank values")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("identity lists cannot contain duplicate values")
        return cleaned

    @field_validator("season_team_ids")
    @classmethod
    def validate_season_team_ids(cls, values: dict[int, int]) -> dict[int, int]:
        for season, team_id in values.items():
            if not 2000 <= season <= 2100 or team_id <= 0:
                raise ValueError("season_team_ids must contain valid seasons and positive team IDs")
        return values


class ManagerMapping(BaseModel):
    """Versioned YAML authority for canonical identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mapping_version: int = Field(default=1, ge=1)
    managers: dict[str, CanonicalManager] = Field(default_factory=dict)

    @field_validator("managers")
    @classmethod
    def validate_manager_keys(
        cls, managers: dict[str, CanonicalManager]
    ) -> dict[str, CanonicalManager]:
        invalid = [key for key in managers if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key)]
        if invalid:
            raise ValueError(
                "manager keys must use lowercase letters, numbers, underscores, or dashes"
            )
        return managers


@dataclass(frozen=True)
class IdentitySuggestion:
    """A non-authoritative candidate generated from stable ESPN owner evidence."""

    suggested_key: str
    display_name: str
    espn_member_ids: tuple[str, ...]
    season_team_ids: tuple[tuple[int, int], ...]
    aliases: tuple[str, ...]
    evidence_count: int


@dataclass(frozen=True)
class IdentityReport:
    """Aggregate reconciliation outcome without private identity values."""

    total_teams: int
    resolved_teams: int
    co_owned_teams: int
    transferred_teams: int
    unresolved_teams: int
    conflict_count: int
    conflicts: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.conflict_count == 0

    @property
    def is_complete(self) -> bool:
        return self.is_valid and self.unresolved_teams == 0


@dataclass(frozen=True)
class IdentityBuildResult:
    """Frames and aggregate report produced by an identity rebuild."""

    frames: dict[str, pd.DataFrame]
    report: IdentityReport


def _canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _owner_ids(row: Any) -> tuple[str, ...]:
    try:
        parsed = json.loads(row.owner_ids_json) if pd.notna(row.owner_ids_json) else []
    except (TypeError, json.JSONDecodeError):
        parsed = []
    values = [str(value) for value in parsed if value]
    if pd.notna(row.primary_owner_id):
        values.append(str(row.primary_owner_id))
    return tuple(dict.fromkeys(values))


def load_manager_mapping(path: Path = DEFAULT_MAPPING_PATH) -> ManagerMapping:
    """Load the ignored YAML mapping without modifying it."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IdentityValidationError(f"Manager mapping is unavailable at {path}.") from exc
    except yaml.YAMLError as exc:
        raise IdentityValidationError("Manager mapping YAML is invalid.") from exc
    try:
        return ManagerMapping.model_validate(raw or {})
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)
        )
        raise IdentityValidationError(f"Manager mapping validation failed: {details}") from exc


def replace_generic_display_names(
    mapping: ManagerMapping, source_managers: pd.DataFrame
) -> tuple[ManagerMapping, int]:
    """Replace numeric ESPN fallback labels with the latest normalized member name."""
    required = {"season", "source_member_id", "display_name"}
    if not required.issubset(source_managers.columns):
        raise IdentityValidationError("Processed manager names lack required source columns.")
    usable = source_managers[
        source_managers["source_member_id"].notna() & source_managers["display_name"].notna()
    ].copy()
    usable["source_member_id"] = usable["source_member_id"].astype(str)
    usable["display_name"] = usable["display_name"].astype(str).str.strip()
    usable = usable[usable["display_name"].ne("")].sort_values("season")

    updated_managers = dict(mapping.managers)
    update_count = 0
    for key, manager in mapping.managers.items():
        if not re.fullmatch(r"espn\d+", manager.display_name, flags=re.IGNORECASE):
            continue
        candidates = usable[usable["source_member_id"].isin(manager.espn_member_ids)]
        if candidates.empty:
            continue
        candidate = str(candidates.iloc[-1]["display_name"])
        if re.fullmatch(r"espn\d+", candidate, flags=re.IGNORECASE):
            continue
        updated_managers[key] = manager.model_copy(update={"display_name": candidate})
        update_count += 1
    return mapping.model_copy(update={"managers": updated_managers}), update_count


def apply_manager_identity_overrides(
    mapping: ManagerMapping,
    *,
    handle_member_ids: dict[str, set[str]],
    renames: dict[str, str],
    deletions: set[str],
) -> tuple[ManagerMapping, int, int]:
    """Rename, merge, or remove canonical entries selected by ESPN display handle."""
    managers = dict(mapping.managers)

    def source_key(handle: str) -> str:
        member_ids = handle_member_ids.get(handle.casefold(), set())
        matches = [
            key
            for key, manager in managers.items()
            if member_ids.intersection(manager.espn_member_ids)
        ]
        if len(member_ids) != 1 or len(matches) != 1:
            raise IdentityValidationError(
                f"Handle {handle!r} must resolve to exactly one member and canonical entry."
            )
        return matches[0]

    renamed = 0
    merged = 0
    for handle, display_name in renames.items():
        key = source_key(handle)
        source = managers[key]
        destinations = [
            candidate_key
            for candidate_key, manager in managers.items()
            if candidate_key != key and manager.display_name.casefold() == display_name.casefold()
        ]
        if len(destinations) > 1:
            raise IdentityValidationError(
                f"Display name {display_name!r} matches multiple canonical entries."
            )
        if not destinations:
            managers[key] = source.model_copy(update={"display_name": display_name})
            renamed += 1
            continue

        destination_key = destinations[0]
        destination = managers[destination_key]
        season_team_ids = dict(destination.season_team_ids)
        for season, team_id in source.season_team_ids.items():
            if season in season_team_ids and season_team_ids[season] != team_id:
                raise IdentityValidationError(
                    f"Cannot merge {handle!r}; season {season} has conflicting team IDs."
                )
            season_team_ids[season] = team_id
        assignments = {
            (item.season, item.source_team_id, item.assignment_type): item
            for item in (*destination.explicit_assignments, *source.explicit_assignments)
        }
        managers[destination_key] = destination.model_copy(
            update={
                "display_name": display_name,
                "espn_member_ids": list(
                    dict.fromkeys((*destination.espn_member_ids, *source.espn_member_ids))
                ),
                "season_team_ids": season_team_ids,
                "aliases": list(dict.fromkeys((*destination.aliases, *source.aliases))),
                "explicit_assignments": list(assignments.values()),
            }
        )
        del managers[key]
        merged += 1

    deleted = 0
    for handle in deletions:
        del managers[source_key(handle)]
        deleted += 1

    remaining_shared: dict[tuple[int, int], list[tuple[str, ExplicitAssignment]]] = defaultdict(
        list
    )
    for manager_key, manager in managers.items():
        for assignment in manager.explicit_assignments:
            remaining_shared[(assignment.season, assignment.source_team_id)].append(
                (manager_key, assignment)
            )
    for (season, team_id), rules in remaining_shared.items():
        if len(rules) != 1:
            continue
        manager_key, orphaned_rule = rules[0]
        manager = managers[manager_key]
        season_team_ids = dict(manager.season_team_ids)
        if season in season_team_ids and season_team_ids[season] != team_id:
            raise IdentityValidationError(
                f"Cannot collapse deleted shared assignment for season {season}."
            )
        season_team_ids[season] = team_id
        managers[manager_key] = manager.model_copy(
            update={
                "season_team_ids": season_team_ids,
                "explicit_assignments": [
                    item for item in manager.explicit_assignments if item != orphaned_rule
                ],
            }
        )
    return mapping.model_copy(update={"managers": managers}), renamed + merged, deleted


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized or "manager"


def suggest_identity_mappings(
    managers: pd.DataFrame, season_teams: pd.DataFrame
) -> list[IdentitySuggestion]:
    """Suggest, but never apply, mappings from stable member/owner identifiers."""
    names_by_member: dict[str, Counter[str]] = defaultdict(Counter)
    for row in managers.itertuples(index=False):
        if pd.notna(row.source_member_id) and pd.notna(row.display_name):
            names_by_member[str(row.source_member_id)][str(row.display_name)] += 1

    teams_by_member: dict[str, set[tuple[int, int]]] = defaultdict(set)
    aliases_by_member: dict[str, set[str]] = defaultdict(set)
    for row in season_teams.itertuples(index=False):
        if pd.isna(row.source_team_id):
            continue
        for member_id in _owner_ids(row):
            teams_by_member[member_id].add((int(row.season), int(row.source_team_id)))
            if pd.notna(row.team_name):
                aliases_by_member[member_id].add(str(row.team_name))

    suggestions: list[IdentitySuggestion] = []
    for member_id in sorted(set(names_by_member) | set(teams_by_member)):
        display_name = (
            names_by_member[member_id].most_common(1)[0][0]
            if names_by_member[member_id]
            else "Unlabeled manager"
        )
        suffix = hashlib.sha256(member_id.encode()).hexdigest()[:8]
        teams = tuple(sorted(teams_by_member[member_id]))
        suggestions.append(
            IdentitySuggestion(
                suggested_key=f"{_slug(display_name)}_{suffix}",
                display_name=display_name,
                espn_member_ids=(member_id,),
                season_team_ids=teams,
                aliases=tuple(sorted(aliases_by_member[member_id])),
                evidence_count=len(teams),
            )
        )
    return suggestions


def write_identity_suggestions(suggestions: Iterable[IdentitySuggestion], path: Path) -> None:
    """Write an ignored, non-authoritative review file that cannot be loaded as a mapping."""
    payload = {
        "notice": "Suggestions only. Review and copy deliberate choices into managers.yaml.",
        "suggestions": [
            {
                "suggested_key": item.suggested_key,
                "display_name": item.display_name,
                "espn_member_ids": list(item.espn_member_ids),
                "season_team_evidence": [
                    {"season": season, "source_team_id": team}
                    for season, team in item.season_team_ids
                ],
                "aliases": list(item.aliases),
                "evidence_count": item.evidence_count,
            }
            for item in suggestions
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    temporary.replace(path)


def _mapping_indexes(
    mapping: ManagerMapping,
) -> tuple[
    dict[str, str],
    dict[tuple[int, int], list[tuple[str, AssignmentType]]],
    list[str],
]:
    member_to_manager: dict[str, str] = {}
    team_rules: dict[tuple[int, int], list[tuple[str, AssignmentType]]] = defaultdict(list)
    conflicts: list[str] = []
    for manager_key, manager in mapping.managers.items():
        for member_id in manager.espn_member_ids:
            previous = member_to_manager.get(member_id)
            if previous is not None and previous != manager_key:
                conflicts.append("A source member identifier is assigned to multiple managers.")
            member_to_manager[member_id] = manager_key
        for season, team_id in manager.season_team_ids.items():
            team_rules[(season, team_id)].append((manager_key, AssignmentType.SINGLE_OWNER))
        for assignment in manager.explicit_assignments:
            team_rules[(assignment.season, assignment.source_team_id)].append(
                (manager_key, assignment.assignment_type)
            )
    return member_to_manager, team_rules, conflicts


def _validate_team_rule(rules: list[tuple[str, AssignmentType]], *, exists: bool) -> str | None:
    if not exists:
        return "A mapping assignment references an unknown season team."
    manager_keys = [key for key, _ in rules]
    kinds = {kind for _, kind in rules}
    if len(manager_keys) != len(set(manager_keys)):
        return "A manager repeats the same season-team assignment."
    if len(rules) == 1 and rules[0][1] != AssignmentType.SINGLE_OWNER:
        return "Co-owner and transfer assignments require at least two managers."
    if len(rules) > 1 and kinds not in (
        {AssignmentType.CO_OWNER},
        {AssignmentType.OWNERSHIP_TRANSFER},
    ):
        return "A season team has conflicting assignment types or multiple single owners."
    return None


def resolve_manager_identities(
    managers: pd.DataFrame, season_teams: pd.DataFrame, mapping: ManagerMapping
) -> IdentityBuildResult:
    """Resolve every source team without mutating Phase 2 frames."""
    member_to_manager, team_rules, conflicts = _mapping_indexes(mapping)
    source_team_keys = {
        (int(row.season), int(row.source_team_id))
        for row in season_teams.itertuples(index=False)
        if pd.notna(row.source_team_id)
    }
    for team_key, rules in team_rules.items():
        error = _validate_team_rule(rules, exists=team_key in source_team_keys)
        if error:
            conflicts.append(error)

    canonical_rows = [
        {
            "canonical_manager_id": manager_key,
            "display_name": manager.display_name,
            "aliases_json": _canonical_json(manager.aliases),
            "espn_member_ids_json": _canonical_json(manager.espn_member_ids),
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        }
        for manager_key, manager in sorted(mapping.managers.items())
    ]
    assignment_rows: list[dict[str, Any]] = []
    unresolved = 0
    resolved = 0
    co_owned = 0
    transferred = 0
    for row in season_teams.sort_values(["season", "source_row_key"]).itertuples(index=False):
        if pd.isna(row.source_team_id):
            conflicts.append("A source team is missing its season-specific team identifier.")
            continue
        team_key = (int(row.season), int(row.source_team_id))
        rules = team_rules.get(team_key, [])
        rule_error = _validate_team_rule(rules, exists=True) if rules else None
        if rule_error:
            rules = []
        owners = _owner_ids(row)
        if not rules:
            candidates = {
                member_to_manager[owner] for owner in owners if owner in member_to_manager
            }
            if len(candidates) == 1:
                rules = [(next(iter(candidates)), AssignmentType.SINGLE_OWNER)]
        if rules:
            resolved += 1
            resolution_type = rules[0][1]
            if resolution_type == AssignmentType.CO_OWNER:
                co_owned += 1
            elif resolution_type == AssignmentType.OWNERSHIP_TRANSFER:
                transferred += 1
        else:
            unresolved += 1
            rules = [(None, "unresolved")]  # type: ignore[list-item]

        for manager_key, resolution_type in rules:
            manager = mapping.managers.get(manager_key) if manager_key is not None else None
            assignment_rows.append(
                {
                    "league_id": int(row.league_id),
                    "season": int(row.season),
                    "source_team_id": int(row.source_team_id),
                    "source_team_row_key": str(row.source_row_key),
                    "source_file": str(row.source_file),
                    "primary_owner_id": (
                        str(row.primary_owner_id) if pd.notna(row.primary_owner_id) else None
                    ),
                    "source_member_ids_json": _canonical_json(list(owners)),
                    "canonical_manager_id": manager_key,
                    "canonical_display_name": manager.display_name if manager else None,
                    "resolution_type": str(resolution_type),
                    "identity_schema_version": IDENTITY_SCHEMA_VERSION,
                }
            )

    frames = {
        "canonical_managers": pd.DataFrame(
            canonical_rows, columns=IDENTITY_TABLE_SCHEMAS["canonical_managers"].names
        ),
        "manager_team_assignments": pd.DataFrame(
            assignment_rows, columns=IDENTITY_TABLE_SCHEMAS["manager_team_assignments"].names
        ),
    }
    unique_conflicts = tuple(dict.fromkeys(conflicts))
    report = IdentityReport(
        total_teams=len(season_teams),
        resolved_teams=resolved,
        co_owned_teams=co_owned,
        transferred_teams=transferred,
        unresolved_teams=unresolved,
        conflict_count=len(unique_conflicts),
        conflicts=unique_conflicts,
    )
    return IdentityBuildResult(frames=frames, report=report)


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_identity_output(
    result: IdentityBuildResult,
    *,
    destination: Path,
    mapping_path: Path,
    processed_root: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name, schema in IDENTITY_TABLE_SCHEMAS.items():
        sort_columns = [
            column
            for column in ("season", "source_team_row_key", "canonical_manager_id")
            if column in result.frames[name]
        ]
        frame = result.frames[name].sort_values(sort_columns, na_position="last")
        table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True)
        pq.write_table(table, destination / f"{name}.parquet", compression="zstd")
    manifest = {
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "mapping_checksum": _file_checksum(mapping_path),
        "source_checksums": {
            name: _file_checksum(processed_root / f"{name}.parquet")
            for name in ("managers", "season_teams")
        },
        "counts": {
            "total_teams": result.report.total_teams,
            "resolved_teams": result.report.resolved_teams,
            "co_owned_teams": result.report.co_owned_teams,
            "transferred_teams": result.report.transferred_teams,
            "unresolved_teams": result.report.unresolved_teams,
            "conflict_count": result.report.conflict_count,
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def rebuild_identity_outputs(
    *,
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    derived_root: Path = DEFAULT_DERIVED_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    require_complete: bool = False,
) -> IdentityBuildResult:
    """Validate and atomically replace resolved identity outputs."""
    mapping = load_manager_mapping(mapping_path)
    try:
        managers = pd.read_parquet(processed_root / "managers.parquet")
        season_teams = pd.read_parquet(processed_root / "season_teams.parquet")
    except (OSError, ValueError) as exc:
        raise IdentityValidationError(
            "Required processed identity inputs are unavailable."
        ) from exc
    result = resolve_manager_identities(managers, season_teams, mapping)
    if not result.report.is_valid:
        raise IdentityValidationError(
            f"Identity mapping has {result.report.conflict_count} conflict(s); "
            "no output was promoted."
        )
    if require_complete and not result.report.is_complete:
        raise IdentityValidationError(
            f"Identity mapping leaves {result.report.unresolved_teams} team(s) unresolved; "
            "no output was promoted."
        )

    transaction = staging_root / f"identities-{uuid.uuid4().hex}"
    staged = transaction / "identities"
    backup = transaction / "backup"
    transaction.mkdir(parents=True, exist_ok=False)
    try:
        _write_identity_output(
            result,
            destination=staged,
            mapping_path=mapping_path,
            processed_root=processed_root,
        )
        try:
            derived_root.parent.mkdir(parents=True, exist_ok=True)
            if derived_root.exists():
                derived_root.replace(backup)
            staged.replace(derived_root)
        except Exception:
            if derived_root.exists():
                shutil.rmtree(derived_root)
            if backup.exists():
                backup.replace(derived_root)
            raise
    finally:
        shutil.rmtree(transaction, ignore_errors=True)
    return result

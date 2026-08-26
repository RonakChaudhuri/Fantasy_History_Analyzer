"""Boundary validation and manifest contracts for ESPN snapshots."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseValidationError(RuntimeError):
    """Raised when ESPN returns a shape that is unsafe to promote."""


class CoverageStatus(StrEnum):
    """Availability states retained instead of coercing missing data to zero."""

    UNAVAILABLE = "unavailable"
    AVAILABLE_EMPTY = "available-empty"
    PARTIAL = "partial"
    COMPLETE = "complete"


class CoverageRecord(BaseModel):
    """Manifest coverage for one source section."""

    model_config = ConfigDict(frozen=True)

    status: CoverageStatus
    row_count: int | None = Field(default=None, ge=0)
    detail: str | None = None


class SnapshotManifest(BaseModel):
    """Versioned description of one validated season snapshot."""

    model_config = ConfigDict(frozen=True)

    manifest_version: int = 1
    importer_version: str
    league_id: int = Field(gt=0)
    season: int = Field(ge=2000, le=2100)
    fetched_at: str
    route: str
    source_checksums: dict[str, str]
    source_shapes: dict[str, list[str]] = Field(default_factory=dict)
    coverage: dict[str, CoverageRecord]
    row_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


SECTION_ROOTS: dict[str, tuple[str, ...]] = {
    "league": ("settings", "teams"),
    "schedule": ("schedule",),
    "draft": ("draftDetail",),
    "rosters": ("teams",),
    "lineups": ("schedule",),
}


def unwrap_league_payload(value: Any, *, season: int) -> tuple[dict[str, Any], bool]:
    """Accept current objects and historical one-item list envelopes."""
    historical = isinstance(value, list)
    if historical:
        if len(value) != 1 or not isinstance(value[0], dict):
            raise ResponseValidationError(
                f"Season {season} returned an invalid historical response envelope."
            )
        value = value[0]
    if not isinstance(value, dict):
        raise ResponseValidationError(f"Season {season} returned a non-object response.")
    return value, historical


def validate_section(section: str, value: Any, *, season: int) -> dict[str, Any]:
    """Validate stable container boundaries while allowing ESPN's dynamic maps."""
    payload, _ = unwrap_league_payload(value, season=season)
    base_section = "lineups" if section.startswith("lineups_") else section
    required = SECTION_ROOTS.get(base_section)
    if required is None:
        raise ResponseValidationError(f"Unknown snapshot section {section!r}.")
    missing = [key for key in required if key not in payload]
    if missing:
        joined = ", ".join(missing)
        raise ResponseValidationError(f"Season {season} {base_section} is missing {joined}.")

    list_roots = {"teams", "schedule", "members"}
    for key in list_roots.intersection(payload):
        if not isinstance(payload[key], list):
            raise ResponseValidationError(f"Season {season} {base_section}.{key} must be an array.")
    if "settings" in payload and not isinstance(payload["settings"], dict):
        raise ResponseValidationError(f"Season {season} league.settings must be an object.")
    if "draftDetail" in payload and not isinstance(payload["draftDetail"], dict):
        raise ResponseValidationError(f"Season {season} draftDetail must be an object.")
    return payload


def validate_league_identity(payload: dict[str, Any], *, league_id: int, season: int) -> None:
    """Prevent a valid-looking response for the wrong league or season from promotion."""
    if payload.get("id") != league_id:
        raise ResponseValidationError(f"Season {season} returned the wrong league identifier.")
    if payload.get("seasonId") != season:
        raise ResponseValidationError(f"Season {season} returned the wrong season identifier.")


def collection_coverage(
    *, present: bool, count: int | None, partial: bool = False, detail: str | None = None
) -> CoverageRecord:
    """Build an explicit coverage state for a source collection."""
    if not present:
        status = CoverageStatus.UNAVAILABLE
        count = None
    elif partial:
        status = CoverageStatus.PARTIAL
    elif count == 0:
        status = CoverageStatus.AVAILABLE_EMPTY
    else:
        status = CoverageStatus.COMPLETE
    return CoverageRecord(status=status, row_count=count, detail=detail)

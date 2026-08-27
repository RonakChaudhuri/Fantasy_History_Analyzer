"""Offline Phase 7 release-readiness and privacy checks."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from fantasy_history.data_access import (
    ANALYTICS_ROOT,
    DRAFT_ANALYTICS_ROOT,
    IDENTITIES_ROOT,
    PROCESSED_ROOT,
    inspect_data_readiness,
)
from fantasy_history.draft_analytics import draft_analytics_bundle_is_current

RELEASE_CHECK_VERSION = "phase7.v1"

MANUAL_RELEASE_GATES = (
    "Reconcile representative early and recent careers and standings against ESPN.",
    "Reconcile every completed-season playoff result against ESPN.",
    "Hand-check one long-running rivalry, sampled records, and one expected-win week.",
    "Reconcile one early and one recent draft plus representative final rosters.",
    "Reproduce sampled draft-value labels and report-card grades from displayed inputs.",
    "Complete desktop, common-phone, keyboard, and rendered-browser privacy journeys.",
    "Exercise private backup/restore, fixture-backed failed refresh, and expired-cookie recovery.",
)

_SECRET_ASSIGNMENT = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?P<name>ESPN_S2|ESPN_SWID)[ \t]*="
    r"[ \t]*(?P<value>.*?)[ \t]*$",
    re.MULTILINE,
)
_PLACEHOLDER_PARTS = (
    "example",
    "placeholder",
    "private-value",
    "replace",
    "secret",
    "your-",
    "your_",
)


@dataclass(frozen=True)
class ReleaseCheck:
    """One share-safe automated release check."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReleaseReport:
    """Automated results plus manual gates that cannot be inferred by code."""

    version: str
    checks: tuple[ReleaseCheck, ...]
    manual_gates: tuple[str, ...]

    @property
    def automated_ready(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def release_ready(self) -> bool:
        # A human must explicitly close and record the manual gates.
        return self.automated_ready and not self.manual_gates

    def model_dump(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "automated_ready": self.automated_ready,
            "release_ready": self.release_ready,
            "checks": [asdict(check) for check in self.checks],
            "manual_gates": list(self.manual_gates),
        }


def _is_prohibited_tracked_path(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    parts = path.parts
    if not parts:
        return False
    if path.name == ".env.example":
        return False
    if path.name == ".env" or path.name.startswith(".env."):
        return True
    if relative_path == ".streamlit/secrets.toml":
        return True
    if relative_path in {
        "data/config/managers.yaml",
        "data/config/managers.suggestions.yaml",
    }:
        return True
    if parts[0] == "exports":
        return True
    if (
        len(parts) >= 2
        and parts[0] == "data"
        and parts[1]
        in {
            "raw",
            "processed",
            "derived",
            "audit",
        }
    ):
        return path.name != ".gitkeep"
    return False


def prohibited_tracked_paths(tracked_paths: Iterable[str]) -> tuple[str, ...]:
    """Return private or generated paths that must never be tracked."""
    return tuple(sorted(path for path in tracked_paths if _is_prohibited_tracked_path(path)))


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").strip().casefold()
    if not normalized:
        return True
    if (normalized.startswith("<") and normalized.endswith(">")) or (
        normalized.startswith("${") and normalized.endswith("}")
    ):
        return True
    return any(part in normalized for part in _PLACEHOLDER_PARTS)


def credential_assignments(text: str) -> tuple[str, ...]:
    """Find non-placeholder ESPN credential assignments without returning their values."""
    return tuple(
        sorted(
            {
                match.group("name")
                for match in _SECRET_ASSIGNMENT.finditer(text)
                if not _looks_like_placeholder(match.group("value"))
            }
        )
    )


def tracked_credential_files(project_root: Path, tracked_paths: Iterable[str]) -> tuple[str, ...]:
    """Return tracked text files containing apparent live credential assignments."""
    findings: list[str] = []
    for relative_path in tracked_paths:
        path = project_root / relative_path
        try:
            if credential_assignments(path.read_text(encoding="utf-8")):
                findings.append(relative_path)
        except (OSError, UnicodeDecodeError):
            continue
    return tuple(sorted(findings))


def inspect_release_readiness(
    *,
    project_root: Path,
    tracked_paths: Iterable[str],
    processed_root: Path = PROCESSED_ROOT,
    identities_root: Path = IDENTITIES_ROOT,
    analytics_root: Path = ANALYTICS_ROOT,
    draft_analytics_root: Path = DRAFT_ANALYTICS_ROOT,
) -> ReleaseReport:
    """Run fast offline checks without mutating data or contacting ESPN."""
    tracked = tuple(tracked_paths)
    readiness = inspect_data_readiness(
        processed_root=processed_root,
        identities_root=identities_root,
        analytics_root=analytics_root,
    )
    core_ready = readiness.ready
    draft_ready = draft_analytics_bundle_is_current(
        processed_root=processed_root,
        identities_root=identities_root,
        draft_analytics_root=draft_analytics_root,
    )
    prohibited = prohibited_tracked_paths(tracked)
    credential_files = tracked_credential_files(project_root, tracked)

    checks = (
        ReleaseCheck(
            "core_bundle_current",
            core_ready,
            readiness.message,
        ),
        ReleaseCheck(
            "draft_bundle_current",
            draft_ready,
            (
                "Draft analytics match processed, identity, formula, and threshold inputs."
                if draft_ready
                else "Draft analytics are missing or stale; rebuild them before release."
            ),
        ),
        ReleaseCheck(
            "private_paths_untracked",
            not prohibited,
            (
                "No prohibited private/generated paths are tracked."
                if not prohibited
                else "Prohibited tracked paths: " + ", ".join(prohibited)
            ),
        ),
        ReleaseCheck(
            "tracked_credentials_absent",
            not credential_files,
            (
                "No apparent ESPN credential assignments were found in tracked text files."
                if not credential_files
                else "Apparent credential assignments found in: " + ", ".join(credential_files)
            ),
        ),
    )
    return ReleaseReport(RELEASE_CHECK_VERSION, checks, MANUAL_RELEASE_GATES)

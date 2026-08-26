#!/usr/bin/env python3
"""Apply reviewed private manager handle overrides with full identity validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from fantasy_history.identities import (
    DEFAULT_MAPPING_PATH,
    DEFAULT_PROCESSED_ROOT,
    ManagerMapping,
    apply_manager_identity_overrides,
    load_manager_mapping,
    resolve_manager_identities,
)
from fantasy_history.validation import IdentityValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply reviewed canonical manager overrides.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument(
        "--rename",
        action="append",
        default=[],
        metavar="HANDLE=DISPLAY_NAME",
        help="Rename a handle, merging it when DISPLAY_NAME already exists.",
    )
    parser.add_argument("--delete", action="append", default=[], metavar="HANDLE")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _parse_renames(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        handle, separator, display_name = value.partition("=")
        if not separator or not handle.strip() or not display_name.strip():
            raise IdentityValidationError("Each --rename must use HANDLE=DISPLAY_NAME.")
        result[handle.strip()] = display_name.strip()
    return result


def _handle_member_ids(raw_root: Path, handles: set[str]) -> dict[str, set[str]]:
    wanted = {handle.casefold() for handle in handles}
    result: dict[str, set[str]] = {handle: set() for handle in wanted}
    for path in sorted(raw_root.glob("*/league.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for member in payload.get("members", []):
            if not isinstance(member, dict):
                continue
            handle = str(member.get("displayName", "")).casefold()
            member_id = str(member.get("id", ""))
            if handle in result and member_id:
                result[handle].add(member_id)
    return result


def main() -> int:
    args = parse_args()
    try:
        renames = _parse_renames(args.rename)
        deletions = {str(value).strip() for value in args.delete if str(value).strip()}
        handles = set(renames) | deletions
        if not handles:
            raise IdentityValidationError("At least one --rename or --delete is required.")
        mapping = load_manager_mapping(args.mapping)
        candidate, changed, deleted = apply_manager_identity_overrides(
            mapping,
            handle_member_ids=_handle_member_ids(args.raw_root, handles),
            renames=renames,
            deletions=deletions,
        )
        managers = pd.read_parquet(args.processed_root / "managers.parquet")
        teams = pd.read_parquet(args.processed_root / "season_teams.parquet")
        report = resolve_manager_identities(managers, teams, candidate).report
        if not report.is_complete:
            raise IdentityValidationError(
                f"Candidate leaves {report.unresolved_teams} unresolved team(s) and "
                f"{report.conflict_count} conflict(s)."
            )
        if args.apply:
            payload = candidate.model_dump(mode="json")
            ManagerMapping.model_validate(payload)
            temporary = args.mapping.with_suffix(args.mapping.suffix + ".tmp")
            temporary.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            temporary.replace(args.mapping)
    except (IdentityValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Identity override failed safely: {exc}")
        return 1
    action = "Applied" if args.apply else "Would apply"
    print(
        f"{action} {changed} rename/merge override(s) and {deleted} deletion(s); "
        f"{report.resolved_teams}/{report.total_teams} teams remain resolved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

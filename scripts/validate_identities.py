#!/usr/bin/env python3
"""Suggest, validate, and atomically rebuild canonical manager identities."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from fantasy_history.identities import (
    DEFAULT_DERIVED_ROOT,
    DEFAULT_MAPPING_PATH,
    DEFAULT_PROCESSED_ROOT,
    DEFAULT_STAGING_ROOT,
    rebuild_identity_outputs,
    suggest_identity_mappings,
    write_identity_suggestions,
)
from fantasy_history.validation import IdentityValidationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical manager identities locally.")
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--derived-root", type=Path, default=DEFAULT_DERIVED_ROOT)
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--write-suggestions",
        type=Path,
        help="Write a private review file; suggestions are never applied automatically.",
    )
    parser.add_argument(
        "--suggest-only",
        action="store_true",
        help="Stop after writing suggestions; requires --write-suggestions.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.suggest_only and not args.write_suggestions:
            raise IdentityValidationError("--suggest-only requires --write-suggestions.")
        if args.write_suggestions:
            managers = pd.read_parquet(args.processed_root / "managers.parquet")
            teams = pd.read_parquet(args.processed_root / "season_teams.parquet")
            suggestions = suggest_identity_mappings(managers, teams)
            write_identity_suggestions(suggestions, args.write_suggestions)
            print(f"Wrote {len(suggestions)} private suggestion(s) for manual review.")
            if args.suggest_only:
                return 0
        result = rebuild_identity_outputs(
            processed_root=args.processed_root,
            mapping_path=args.mapping,
            derived_root=args.derived_root,
            staging_root=args.staging_root,
            require_complete=args.require_complete,
        )
    except (IdentityValidationError, OSError, ValueError) as exc:
        print(f"Identity validation failed safely: {exc}")
        return 1
    report = result.report
    print(
        "Identity validation passed: "
        f"{report.total_teams} team(s), {report.resolved_teams} resolved, "
        f"{report.co_owned_teams} co-owned, {report.transferred_teams} transferred, "
        f"{report.unresolved_teams} unresolved, {report.conflict_count} conflicts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

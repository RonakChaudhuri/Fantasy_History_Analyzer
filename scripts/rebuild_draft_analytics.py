#!/usr/bin/env python3
"""Rebuild versioned draft-value analytics without contacting ESPN."""

from __future__ import annotations

import argparse
from pathlib import Path

from fantasy_history.draft_analytics import (
    DraftAnalyticsValidationError,
    rebuild_draft_analytics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--identities-root", type=Path, default=Path("data/derived/identities"))
    parser.add_argument(
        "--draft-analytics-root", type=Path, default=Path("data/derived/draft_analytics")
    )
    parser.add_argument("--staging-root", type=Path, default=Path("data/.staging"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = rebuild_draft_analytics(
            processed_root=args.processed_root,
            identities_root=args.identities_root,
            draft_analytics_root=args.draft_analytics_root,
            staging_root=args.staging_root,
        )
    except (DraftAnalyticsValidationError, OSError, ValueError) as exc:
        print(f"Draft analytics rebuild failed safely: {exc}")
        return 1
    counts = ", ".join(f"{name}={len(frame)}" for name, frame in result.frames.items())
    print(f"Draft analytics rebuild passed: {counts}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

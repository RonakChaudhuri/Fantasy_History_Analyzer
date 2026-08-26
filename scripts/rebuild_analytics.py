#!/usr/bin/env python3
"""Rebuild the versioned analytics bundle without contacting ESPN."""

from __future__ import annotations

import argparse
from pathlib import Path

from fantasy_history.analytics import AnalyticsValidationError, rebuild_analytics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--identities-root", type=Path, default=Path("data/derived/identities"))
    parser.add_argument("--analytics-root", type=Path, default=Path("data/derived/analytics"))
    parser.add_argument("--staging-root", type=Path, default=Path("data/.staging"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = rebuild_analytics(
            processed_root=args.processed_root,
            identities_root=args.identities_root,
            analytics_root=args.analytics_root,
            staging_root=args.staging_root,
        )
    except (AnalyticsValidationError, OSError, ValueError) as exc:
        print(f"Analytics rebuild failed safely: {exc}")
        return 1
    counts = ", ".join(f"{name}={len(frame)}" for name, frame in result.frames.items())
    print(f"Analytics rebuild passed: {counts}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

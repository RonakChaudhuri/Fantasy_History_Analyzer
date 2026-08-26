#!/usr/bin/env python3
"""Validate local raw snapshots and processed-table integrity without ESPN access."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from fantasy_history.importer import (
    DEFAULT_PROCESSED_ROOT,
    DEFAULT_RAW_ROOT,
    ImportPipelineError,
    load_season_snapshot,
    validate_frames,
)
from fantasy_history.normalization import TABLE_SCHEMAS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local Fantasy History data.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshots = sorted(
            (path for path in args.raw_root.iterdir() if path.is_dir() and path.name.isdigit()),
            key=lambda path: int(path.name),
        )
        for snapshot in snapshots:
            load_season_snapshot(snapshot)
        frames = {
            name: pd.read_parquet(args.processed_root / f"{name}.parquet") for name in TABLE_SCHEMAS
        }
        errors = validate_frames(frames)
        if errors:
            raise ImportPipelineError("; ".join(errors))
    except (ImportPipelineError, OSError, ValueError) as exc:
        print(f"Validation failed: {exc}")
        return 1
    print(f"Validated {len(snapshots)} snapshot(s) and {len(frames)} processed tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Rebuild normalized Parquet tables from local raw snapshots only."""

from __future__ import annotations

from fantasy_history.importer import ImportPipelineError, rebuild_processed


def main() -> int:
    try:
        frames = rebuild_processed()
    except (ImportPipelineError, OSError, ValueError) as exc:
        print(f"Rebuild failed safely: {exc}")
        return 1
    print(f"Rebuilt {len(frames)} tables with {sum(map(len, frames.values()))} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

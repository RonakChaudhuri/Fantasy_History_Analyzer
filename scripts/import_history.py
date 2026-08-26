#!/usr/bin/env python3
"""Explicit credentialed ESPN import command; Streamlit never calls this module."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from fantasy_history.config import ConfigurationError, load_settings
from fantasy_history.espn_client import EspnClient, EspnClientError
from fantasy_history.importer import ImportPipelineError, import_seasons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import ESPN fantasy history safely.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--season", type=int, help="Import one season.")
    mode.add_argument("--all", action="store_true", help="Import first through latest season.")
    mode.add_argument("--latest", action="store_true", help="Refresh only the latest season.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_settings()
        with EspnClient(settings) as client:
            latest = (
                args.season
                if args.season is not None
                else client.discover_latest(current_year=datetime.now(UTC).year)
            )
            seasons = list(range(settings.first_season, latest + 1)) if args.all else [latest]
            frames = import_seasons(settings, seasons, client=client)
    except (ConfigurationError, EspnClientError, ImportPipelineError, ValueError) as exc:
        print(f"Import failed safely: {exc}")
        return 1
    rows = sum(len(frame) for frame in frames.values())
    print(f"Imported {len(seasons)} season(s); validated {rows} normalized rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

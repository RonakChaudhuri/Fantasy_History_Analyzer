#!/usr/bin/env python3
"""Safely replace generic canonical labels with source-backed member names."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from fantasy_history.identities import (
    DEFAULT_MAPPING_PATH,
    DEFAULT_PROCESSED_ROOT,
    ManagerMapping,
    load_manager_mapping,
    replace_generic_display_names,
)
from fantasy_history.validation import IdentityValidationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace numeric ESPN manager labels using normalized first/last names."
    )
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Atomically update the ignored canonical YAML; otherwise perform a dry run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        mapping = load_manager_mapping(args.mapping)
        managers = pd.read_parquet(args.processed_root / "managers.parquet")
        updated, count = replace_generic_display_names(mapping, managers)
        if args.apply and count:
            payload = updated.model_dump(mode="json")
            # Validate the serialized representation before replacing the authority file.
            ManagerMapping.model_validate(payload)
            temporary = args.mapping.with_suffix(args.mapping.suffix + ".tmp")
            temporary.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            temporary.replace(args.mapping)
    except (IdentityValidationError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Manager label update failed safely: {exc}")
        return 1
    action = "Updated" if args.apply else "Would update"
    print(f"{action} {count} generic manager label(s); no identity assignments changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

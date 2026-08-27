#!/usr/bin/env python3
"""Run fast, offline Phase 7 release and privacy preflight checks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from fantasy_history.release import inspect_release_readiness

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a share-safe JSON report instead of human-readable output.",
    )
    return parser.parse_args()


def _version_control_paths(project_root: Path) -> tuple[str, ...]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required for the tracked-file privacy check.")
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    return tuple(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)


def main() -> int:
    args = parse_args()
    try:
        report = inspect_release_readiness(
            project_root=PROJECT_ROOT,
            tracked_paths=_version_control_paths(PROJECT_ROOT),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        print(f"Release preflight failed safely: {exc}")
        return 1

    if args.json:
        print(json.dumps(report.model_dump(), indent=2, sort_keys=True))
    else:
        for check in report.checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}")
        print(f"Manual release gates remaining: {len(report.manual_gates)}")
        for gate in report.manual_gates:
            print(f"- {gate}")
        if report.automated_ready:
            print("Automated preflight passed; manual release gates remain open.")
        else:
            print("Automated preflight failed; resolve failed checks before release.")
    return 0 if report.automated_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the sanitized data bundle used by the public Streamlit deployment."""

from fantasy_history.deployment import build_deployment_bundle


def main() -> int:
    build_deployment_bundle()
    print("Public deployment bundle rebuilt without credentials, raw responses, or member IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

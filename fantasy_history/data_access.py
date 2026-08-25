"""File-backed reads for UI-ready data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OVERVIEW_PATH = PROJECT_ROOT / "data" / "fixtures" / "demo_overview.json"


def load_demo_overview(path: Path = DEMO_OVERVIEW_PATH) -> dict[str, Any]:
    """Load the committed synthetic overview fixture without network access."""
    with path.open(encoding="utf-8") as fixture:
        payload = json.load(fixture)
    if not isinstance(payload, dict):
        raise ValueError("The demo overview fixture must contain a JSON object.")
    return payload


def champions_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert synthetic champion rows into a chart-ready frame."""
    return pd.DataFrame(payload["champions"])

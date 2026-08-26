"""Shared presentation formatting helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def is_available(value: Any) -> bool:
    """Return false for None and pandas/NumPy missing values."""
    return value is not None and not bool(pd.isna(value))


def format_points(value: float | None) -> str:
    """Format fantasy points consistently for display."""
    if value is None or bool(pd.isna(value)):
        return "Unavailable"
    return f"{float(value):,.2f}"


def format_percentage(value: float | None) -> str:
    """Format a ratio without converting missing data to zero."""
    if value is None or bool(pd.isna(value)):
        return "Unavailable"
    return f"{float(value):.3f}"


def format_integer(value: float | int | None) -> str:
    """Format an integer-like value while preserving unavailable state."""
    if value is None or bool(pd.isna(value)):
        return "Unavailable"
    return f"{int(value):,}"


def format_signed(value: float | None, *, decimals: int = 2) -> str:
    """Format luck and margins with an explicit sign."""
    if value is None or bool(pd.isna(value)):
        return "Unavailable"
    return f"{float(value):+,.{decimals}f}"


def format_record(wins: Any, losses: Any, ties: Any) -> str:
    """Format W-L-T, retaining an unavailable state when inputs are missing."""
    if not all(is_available(value) for value in (wins, losses, ties)):
        return "Unavailable"
    return f"{int(wins)}-{int(losses)}-{int(ties)}"

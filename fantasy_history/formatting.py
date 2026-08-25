"""Shared presentation formatting helpers."""

from __future__ import annotations


def format_points(value: float) -> str:
    """Format fantasy points consistently for display."""
    return f"{value:,.2f}"

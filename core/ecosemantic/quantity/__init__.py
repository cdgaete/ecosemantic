"""A quantity as the canvas and the map write it."""

from __future__ import annotations

from ecosemantic.model.units import symbol


def written(amount: float, unit: str) -> str:
    """Three significant figures with thousands grouped, then the unit's symbol."""
    if amount == 0:
        return f"0 {symbol(unit)}"
    digits = f"{amount:.3g}"
    value = float(digits)
    text = f"{value:,.0f}" if abs(value) >= 1000 else digits
    return f"{text} {symbol(unit)}"

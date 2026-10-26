from __future__ import annotations

import pytest

from ecosemantic.quantity import written


@pytest.mark.parametrize(
    ("amount", "unit", "text"),
    [
        (168.18, "kg", "168 kg"),
        (3.6819, "kg", "3.68 kg"),
        (0.049124, "kilowatt hour", "0.0491 kWh"),
        (168.18, "kilogram", "168 kg"),
        (2.5, "ton kilometer", "2.5 tkm"),
        (1250.4, "MJ", "1,250 MJ"),
        (0.0, "kg", "0 kg"),
    ],
)
def test_an_amount_is_written_in_three_significant_figures_and_the_units_symbol(
    amount: float, unit: str, text: str
) -> None:
    assert written(amount, unit) == text

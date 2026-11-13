from __future__ import annotations

import pytest

from ecosemantic.ports.search import phrases, spellings


def test_a_cas_number_is_matched_bare_and_padded_with_zeros_to_six_digits() -> None:
    [bare] = phrases("124-38-9")
    assert spellings(bare) == ("124", "000124")
    [padded] = phrases("000124-38-9")
    assert spellings(padded) == ("000124", "124")
    [seven] = phrases("1234567-89-0")
    assert spellings(seven) == ("1234567",)


@pytest.mark.parametrize(
    "query", ["steel", "pm2.5", "1-3mw", "24-97-2x", "124-38-9*", "5-10-3", "12345678-12-1"]
)
def test_a_term_that_is_no_cas_number_is_matched_as_it_is_written(query: str) -> None:
    [phrase] = phrases(query)
    assert spellings(phrase) == (phrase.tokens[0],)

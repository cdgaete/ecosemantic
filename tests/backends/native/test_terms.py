import sqlite3
import unicodedata

import pytest

from ecosemantic.backends.native.terms import tokens

TEXTS = [
    "steel production",
    "PM2.5 emission, low-voltage",
    "Cátodo de cobre — Chile (ruta pirometalúrgica)",
    "Straße Ærø øre œuvre ﬁne",
    "m³ CO₂ 1,4-dioxane",
    "electricity, high voltage {CH}| market for | Cut-off, U",
    "naïve café ÉCOLE Ångström İstanbul",
    "Ελληνικά ΆΈΉ",
    "日本語テキスト",
    "tab\tnew\nline x_y a'b ₂ ² ½",
    unicodedata.normalize("NFD", "Cátodo naïve Ångström"),
    "ḁ ṩ ẞ ǖ ǘ ǅungla",
]


@pytest.fixture(scope="module")
def fts5() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE f USING fts5(t, tokenize='unicode61')")
    connection.execute("CREATE VIRTUAL TABLE v USING fts5vocab(f, 'instance')")
    for row, text in enumerate(TEXTS, start=1):
        connection.execute("INSERT INTO f(rowid, t) VALUES (?, ?)", (row, text))
    return connection


@pytest.mark.parametrize("row", range(1, len(TEXTS) + 1))
def test_tokens_are_the_tokens_fts5_unicode61_writes(fts5: sqlite3.Connection, row: int) -> None:
    written = fts5.execute("SELECT term FROM v WHERE doc = ? ORDER BY offset", (row,))
    assert tokens(TEXTS[row - 1]) == [term for (term,) in written]


def test_no_text_has_no_tokens() -> None:
    assert tokens(None) == [] and tokens("") == [] and tokens(" — , ") == []

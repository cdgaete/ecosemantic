"""The one tokenizer of the catalog's search, SQLite FTS5's `unicode61` with its defaults: the
diacritic of a Latin letter that carries one removed, lowercased, and split at every character
that is not a letter, a number or for private use."""

from __future__ import annotations

import unicodedata

_KEPT = ("L", "N")


def _kept(character: str) -> bool:
    category = unicodedata.category(character)
    return category[0] in _KEPT or category == "Co"


def _plain(character: str) -> str:
    """A Latin letter carrying one diacritic without it; any other character as it is."""
    if not unicodedata.name(character, "").startswith("LATIN"):
        return character
    parts = unicodedata.normalize("NFD", character)
    marks = [c for c in parts if unicodedata.category(c) == "Mn"]
    if len(marks) != 1:
        return character
    return "".join(c for c in parts if c not in marks)


def tokens(text: str | None) -> list[str]:
    """The tokens of a text in order, none for no text."""
    if not text:
        return []
    plain = "".join(_plain(c) for c in unicodedata.normalize("NFC", text)).lower()
    found: list[str] = []
    current: list[str] = []
    for character in plain:
        if _kept(character):
            current.append(character)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found

from __future__ import annotations

import dataclasses

from ecosemantic.databases.bafu.setup import Prepared as BafuPrepared
from ecosemantic.databases.prepared import PreparedRelease
from ecosemantic.databases.uslci.setup import Prepared as UsLciPrepared


def test_a_uslci_and_a_bafu_preparation_are_prepared_releases() -> None:
    declared = {field.name for field in dataclasses.fields(PreparedRelease)}
    for prepared in (UsLciPrepared, BafuPrepared):
        assert issubclass(prepared, PreparedRelease)
        own = prepared.__annotations__
        assert declared.isdisjoint(own)

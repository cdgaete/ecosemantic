"""A resolver over dictionaries, for the tests that write a package without a background."""

from __future__ import annotations

from ecosemantic.errors import NotFound
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.resolver import BackgroundInfo, FlowInfo


class DictResolver:
    """A resolver over dictionaries keyed by native id."""

    def __init__(
        self, backgrounds: dict[str, BackgroundInfo], elementary_flows: dict[str, FlowInfo]
    ) -> None:
        self._backgrounds = backgrounds
        self._flows = elementary_flows

    def background(self, ref: BackgroundRef) -> BackgroundInfo:
        if ref.id not in self._backgrounds:
            raise NotFound(f"no background process {ref.id!r} in {ref.database!r}")
        return self._backgrounds[ref.id]

    def flow(self, ref: ElementaryFlowRef) -> FlowInfo:
        if ref.id not in self._flows:
            raise NotFound(f"no elementary flow {ref.id!r} in {ref.database!r}")
        return self._flows[ref.id]

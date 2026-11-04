"""The resolver's contract. Subclass with the fixtures `resolver`, `known_background`,
`known_background_info`, `known_flow` and `known_flow_info`."""

from __future__ import annotations

import pytest

from ecosemantic.errors import NotFound
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.resolver import BackgroundInfo, FlowInfo, Resolver


class ResolverConformance:
    def test_a_known_background_resolves_to_its_name_and_unit(
        self,
        resolver: Resolver,
        known_background: BackgroundRef,
        known_background_info: BackgroundInfo,
    ) -> None:
        assert resolver.background(known_background) == known_background_info

    def test_an_unknown_background_is_not_found(
        self, resolver: Resolver, known_background: BackgroundRef
    ) -> None:
        unknown = known_background.model_copy(update={"id": "no-such-process"})
        with pytest.raises(NotFound):
            resolver.background(unknown)

    def test_a_known_flow_resolves_to_its_compartment_and_type(
        self, resolver: Resolver, known_flow: ElementaryFlowRef, known_flow_info: FlowInfo
    ) -> None:
        assert resolver.flow(known_flow) == known_flow_info

    def test_an_unknown_flow_is_not_found(
        self, resolver: Resolver, known_flow: ElementaryFlowRef
    ) -> None:
        unknown = known_flow.model_copy(update={"id": "no-such-flow"})
        with pytest.raises(NotFound):
            resolver.flow(unknown)

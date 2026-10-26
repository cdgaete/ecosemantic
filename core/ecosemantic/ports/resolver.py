"""The names a package writer needs for background references, looked up synchronously."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, computed_field, model_validator

from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.types import FlowType, Side, flow_side


class BackgroundInfo(BaseModel):
    name: str
    reference_product: str
    location: str | None
    unit: str


class FlowInfo(BaseModel):
    name: str
    compartment: str
    sub_compartment: str | None
    unit: str
    flow_type: FlowType

    @model_validator(mode="after")
    def _placed(self) -> FlowInfo:
        flow_side(self.flow_type, self.sub_compartment)
        return self

    @computed_field
    @property
    def side(self) -> Side:
        """Input or output, by the flow's type and sub-compartment."""
        return flow_side(self.flow_type, self.sub_compartment)


@runtime_checkable
class Resolver(Protocol):
    def background(self, ref: BackgroundRef) -> BackgroundInfo: ...

    def flow(self, ref: ElementaryFlowRef) -> FlowInfo: ...

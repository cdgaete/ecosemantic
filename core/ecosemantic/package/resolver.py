"""A resolver over an inventory port; the package writer calls it synchronously."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.resolver import BackgroundInfo, FlowInfo

T = TypeVar("T")


class InventoryResolver:
    """A resolver over an inventory port; one loop serves every lookup, whoever the caller."""

    def __init__(self, inventory: InventoryPort) -> None:
        self._inventory = inventory
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self, lookup: Coroutine[Any, Any, T]) -> T:
        """One lookup to completion; the lock keeps the loop's single user at a time."""
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            return self._loop.run_until_complete(lookup)

    def close(self) -> None:
        """Close the loop, so a lookup after this builds a fresh one."""
        with self._lock:
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    def background(self, ref: BackgroundRef) -> BackgroundInfo:
        process = self._run(self._inventory.get_process(ref))
        return BackgroundInfo(
            name=process.name,
            reference_product=process.reference_product,
            location=process.location,
            unit=process.unit,
        )

    def flow(self, ref: ElementaryFlowRef) -> FlowInfo:
        flow = self._run(self._inventory.get_elementary_flow(ref))
        return FlowInfo(
            name=flow.name,
            compartment=flow.compartment,
            sub_compartment=flow.sub_compartment,
            unit=flow.unit,
            flow_type=flow.flow_type,
        )

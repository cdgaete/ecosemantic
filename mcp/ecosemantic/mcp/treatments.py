"""The treatments among a product system's background inputs, asked of the inventory port, and
the exchanges sending a positive amount to one."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from ecosemantic.compute.edits import background_references
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.model.validation import sent_backwards
from ecosemantic.ports.inventory import InventoryPort


async def treatments_in(
    inventory: InventoryPort, documents: Sequence[ProductSystem]
) -> frozenset[BackgroundRef] | None:
    """The treatments among the background inputs these documents name on the first one's
    database, or None when the store does not serve that database, so no case of waste sent to
    a treatment can be stated for it."""
    database = documents[0].database.name
    if database not in {d.name for d in await inventory.list_databases()}:
        return None
    sent = [
        ref
        for document in documents
        for _, _, ref in background_references(document)
        if isinstance(ref, BackgroundRef) and ref.database == database
    ]
    return frozenset(await inventory.treatments(sent))


def named_backwards(
    document: ProductSystem,
    linked: Mapping[uuid.UUID, ProductSystem],
    treatments: frozenset[BackgroundRef] | None,
) -> list[str]:
    """Each product exchange of a materialised document, and of the systems it links under their
    names, that sends a positive amount to one of `treatments`, which runs it backwards; none
    when the treatments are unknown."""
    if treatments is None:
        return []
    documents = [(None, document), *((d.name, d) for d in linked.values())]
    return [b.named for b in sent_backwards(documents, treatments)]


async def backwards_in(
    inventory: InventoryPort, document: ProductSystem, linked: Mapping[uuid.UUID, ProductSystem]
) -> list[str]:
    """`named_backwards` over the treatments the inventory port finds among the inputs of a
    materialised document and of the systems it links."""
    treatments = await treatments_in(inventory, [document, *linked.values()])
    return named_backwards(document, linked, treatments)

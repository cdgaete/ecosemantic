"""The home page's rows: every stored product system's card with its process count, its last
change, its validation and its open requests, in one answer."""

from __future__ import annotations

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import EcoSemanticError, ErrorEnvelope, error_payload
from ecosemantic.mcp.context import Callers, ServerContext
from ecosemantic.mcp.envelopes import REMEDIES, Answer
from ecosemantic.mcp.systems import (
    SystemCard,
    get_product_system,
    list_product_systems,
    validate_product_system,
)
from ecosemantic.model.validation import ValidationReport
from ecosemantic.ports.types import LogEntry
from ecosemantic.view.handling import for_caller


class SystemRow(BaseModel):
    """What the home page shows of one product system."""

    system: SystemCard
    processes: int
    last: LogEntry
    validation: ValidationReport | None
    unvalidated: ErrorEnvelope | None
    open_requests: int


async def _row(context: ServerContext, card: SystemCard) -> SystemRow:
    """One card as the row the home page draws, with its validation report or, when validation
    cannot run, the envelope the validation route answers for it."""
    read = await get_product_system(context, str(card.id))
    last = (await context.storage.log(card.id))[-1]
    report: ValidationReport | None = None
    unvalidated: ErrorEnvelope | None = None
    try:
        report = (await validate_product_system(context, str(card.id))).value
    except EcoSemanticError as exc:
        unvalidated = error_payload(exc, REMEDIES)
    return SystemRow(
        system=card,
        processes=len(read.value.processes),
        last=last,
        validation=report,
        unvalidated=unvalidated,
        open_requests=read.open_requests,
    )


def routes(callers: Callers) -> list[Route]:
    """The one resource the home page reads: a row for every product system of the request's
    caller."""

    @for_caller(callers)
    async def home(request: Request, context: ServerContext) -> Response:
        cards = (await list_product_systems(context)).value
        rows = [await _row(context, card) for card in cards]
        return JSONResponse(Answer[list[SystemRow]](value=rows).model_dump(mode="json"))

    return [Route("/api/home", home)]

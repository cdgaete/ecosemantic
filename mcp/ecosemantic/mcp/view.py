"""The tool that answers the link to the page, whole or at one product system."""

from __future__ import annotations

from fastmcp import FastMCP

from ecosemantic.errors import NotSupported
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ
from ecosemantic.mcp.envelopes import Answer, as_uuid, bound, boundary


async def view_link(context: ServerContext, product_system_id: str | None = None) -> Answer[str]:
    if context.view_url is None:
        raise NotSupported("this server serves no view")
    if product_system_id is None:
        return Answer[str](value=context.view_url)
    link = context.deep_link(as_uuid(product_system_id))
    if link is None:
        raise NotSupported("this server serves no view")
    return Answer[str](value=link)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the view tool."""
    server.tool(
        name="view_link",
        annotations=READ,
        description=(
            "The link to the page the person watches the model in, or the page of one "
            "product system when given its id."
        ),
    )(boundary(bound(view_link, context)))

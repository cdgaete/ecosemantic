"""What the bridge publishes at its well-known address, and what an engine registers as and is
registered with."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

WELL_KNOWN = "/.well-known/ecosemantic-bridge"


class _Document(BaseModel):
    """One document of the bridge's discovery, frozen: what the bridge answers and what an engine
    sends it."""

    model_config = ConfigDict(frozen=True)


class BridgeConfiguration(_Document):
    """The bridge's discovery document: the issuer, the browser's and the device's client ids, the
    tunnel's resource, scope and address, and the connector's and the registration's addresses."""

    issuer: str
    browser_client_id: str
    device_client_id: str
    tunnel_resource: str
    tunnel_scope: str
    tunnel_url: str
    connector_url: str
    registration_url: str


class Registration(_Document):
    """What an engine registers: itself when it has an id, the name it answers to and its
    version."""

    engine: UUID | None
    name: str
    version: str


class Registered(_Document):
    """What the bridge answers a registration with: the engine, its account, its handle and the
    page's address."""

    engine: UUID
    account: str
    handle: str
    page_url: str

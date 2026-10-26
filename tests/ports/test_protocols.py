from __future__ import annotations

import uuid

from ecosemantic.ports.calculation import CalculationPort
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.search import SearchPort
from ecosemantic.ports.storage import StoragePort


class FakeStorage:
    async def list_product_systems(self):
        return []

    async def get_product_system(self, product_system_id: uuid.UUID):
        raise NotImplementedError

    async def get_version(self, product_system_id: uuid.UUID, content_hash: str):
        raise NotImplementedError

    async def put_product_system(self, product_system, actor, message):
        raise NotImplementedError

    async def delete_product_system(self, product_system_id: uuid.UUID, actor):
        raise NotImplementedError

    async def log(self, product_system_id: uuid.UUID):
        return []

    async def get_layout(self, product_system_id: uuid.UUID):
        raise NotImplementedError

    async def put_layout(self, product_system_id: uuid.UUID, layout):
        raise NotImplementedError

    async def post_request(self, product_system_id: uuid.UUID, draft):
        raise NotImplementedError

    async def list_requests(self, product_system_id: uuid.UUID, open_only: bool = False):
        return []

    async def resolve_request(self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome):
        raise NotImplementedError

    async def return_package(
        self, product_system_id: uuid.UUID, exported_root, actor, at_entry=None
    ):
        raise NotImplementedError

    async def export_package(self, product_system_id: uuid.UUID, destination):
        raise NotImplementedError

    async def restore_package(self, source):
        raise NotImplementedError

    def changes(self):
        raise NotImplementedError


class Incomplete:
    async def list_product_systems(self):
        return []


def test_complete_fake_satisfies_storage_port() -> None:
    assert isinstance(FakeStorage(), StoragePort)
    assert not isinstance(Incomplete(), StoragePort)


def test_other_ports_are_runtime_checkable() -> None:
    for port in (InventoryPort, SearchPort, CalculationPort):
        assert not isinstance(Incomplete(), port)

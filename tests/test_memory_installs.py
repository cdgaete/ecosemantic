from __future__ import annotations

import uuid

import pytest

from ecosemantic.ports.install import InstallLauncher, InstallPort
from ecosemantic.ports.types import Account, DatabaseSource
from tests.conformance.installs import InstallConformance
from tests.memory_installs import MemoryInstaller, MemoryInstalls


class TestMemoryInstalls(InstallConformance):
    @pytest.fixture
    def installs(self) -> MemoryInstalls:
        return MemoryInstalls()

    def test_satisfies_the_port(self, installs: MemoryInstalls) -> None:
        assert isinstance(installs, InstallPort)


def sources() -> list[DatabaseSource]:
    return [
        DatabaseSource(
            name="uslci", versions=["2026"], system_models=[], credential=None, terms=False
        )
    ]


def test_the_memory_installer_answers_the_sources_it_was_built_with() -> None:
    launcher: InstallLauncher = MemoryInstaller(sources())
    assert launcher.sources() == sources()


def test_the_memory_installer_records_who_it_starts_and_names_pid_4242() -> None:
    installer = MemoryInstaller(sources())
    account = Account(username="carlos", password="s3cret")
    install_id = uuid.uuid4()
    assert installer.start(install_id, account) == 4242
    assert installer.start(uuid.UUID(int=2), None) == 4242
    assert installer.started == [(install_id, account), (uuid.UUID(int=2), None)]


def test_the_memory_installer_holds_every_install_alive_unless_it_is_named_dead() -> None:
    installer = MemoryInstaller(sources())
    live, dead = uuid.UUID(int=1), uuid.UUID(int=2)
    installer.dead.add(dead)
    assert installer.alive(live) is True
    assert installer.alive(dead) is False

"""The launchers' contracts. Subclass with a `launcher` fixture."""

from __future__ import annotations

import uuid

from ecosemantic.model.entities import Actor
from ecosemantic.ports.install import InstallLauncher
from ecosemantic.ports.run import RunLauncher
from ecosemantic.ports.types import InstallDraft


class RunLauncherConformance:
    def test_a_run_never_started_is_not_alive(self, launcher: RunLauncher) -> None:
        assert launcher.alive(uuid.uuid4()) is False


class InstallLauncherConformance:
    def test_an_install_never_started_is_not_alive(self, launcher: InstallLauncher) -> None:
        assert launcher.alive(uuid.uuid4()) is False

    def test_an_openlca_draft_installs_under_the_name_it_gives(
        self, launcher: InstallLauncher
    ) -> None:
        draft = InstallDraft(
            source="openlca",
            actor=Actor(kind="person", name="carlos"),
            version="1",
            system_model="unit process",
            package="fixture.zip",
            name="my-database",
        )
        assert launcher.database(draft) == "my-database"

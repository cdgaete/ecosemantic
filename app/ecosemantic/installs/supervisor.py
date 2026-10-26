"""Starting the process that carries an install on this machine, and the sources it may come
from."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from ecosemantic.backends.filesystem.installs import install_dir
from ecosemantic.backends.filesystem.run_folder import LOG_FILE, heartbeat_age
from ecosemantic.compute.accounts import without_credentials
from ecosemantic.databases.bafu.profile import versions as bafu_versions
from ecosemantic.databases.ecoinvent.profile import profiled
from ecosemantic.databases.uslci.profile import versions as uslci_versions
from ecosemantic.installs.handover import encoded
from ecosemantic.ports.types import STALE_SECONDS, Account, DatabaseSource, source_credential
from ecosemantic.runs.supervisor import start_detached


class LocalInstaller:
    """Carries each install in a worker process on this machine, reading the sources from their
    profiles and handing the account over on that process's standard input."""

    def __init__(self, data: Path) -> None:
        self.data = data

    def sources(self) -> list[DatabaseSource]:
        """Every source an install may come from, with the versions its profiles pin, the system
        models it holds, and the credential and terms its install needs."""
        releases = profiled()
        return [
            DatabaseSource(
                name="openlca",
                versions=[],
                system_models=["unit process"],
                credential=source_credential("openlca"),
                terms=False,
            ),
            DatabaseSource(
                name="uslci",
                versions=list(uslci_versions()),
                system_models=[],
                credential=source_credential("uslci"),
                terms=False,
            ),
            DatabaseSource(
                name="bafu",
                versions=list(bafu_versions()),
                system_models=[],
                credential=source_credential("bafu"),
                terms=True,
            ),
            DatabaseSource(
                name="ecoinvent",
                versions=list(dict.fromkeys(version for version, _model in releases)),
                system_models=list(dict.fromkeys(model for _version, model in releases)),
                credential=source_credential("ecoinvent"),
                terms=False,
            ),
        ]

    def start(self, install_id: uuid.UUID, account: Account | None) -> int:
        """Start the process that carries one install, apart from the server, with the account on
        its standard input and an environment holding none of the variables a credential travels
        in."""
        command = [
            sys.executable,
            "-m",
            "ecosemantic.installs.worker",
            "--data-dir",
            str(self.data),
            "--install",
            str(install_id),
        ]
        return start_detached(
            command,
            install_dir(self.data, install_id) / LOG_FILE,
            stdin=encoded(account),
            environment=without_credentials(os.environ),
        )

    def alive(self, install_id: uuid.UUID) -> bool:
        """Whether the process carrying this install beat its heartbeat within `STALE_SECONDS`."""
        age = heartbeat_age(install_dir(self.data, install_id))
        return age is not None and age <= STALE_SECONDS

"""The four end-to-end checks of an installed `ecosemantic` command, as a chatbot would drive it:
a stdio server answering `initialize` and listing its tools; a product system whose name carries
accents, through the tools, an export and an import; a Monte Carlo run started, cancelled and
reported; and a database installed from the fixture's bundle through the tools, named by the same
server that installed it. It installs the synthetic fixture with the command's own `setup openlca`,
and prints one JSON report; it exits 1 when a check fails.

    python scripts/end_to_end.py [--command PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecosemantic.cli.clients import installed_command  # noqa: E402
from ecosemantic.mcp.server import ROSTER  # noqa: E402
from tests.engine_fixture import fixture_bundle  # noqa: E402
from tests.fixture_data import CODES, FIXTURE_DB  # noqa: E402

TELEMETRY_OFF = {"ECOSEMANTIC_TELEMETRY": "off"}
ACCENTED = "Cátodo de cobre — Chile (ruta pirometalúrgica), ñandú"
INSTALLED = "fixture-installed"
SETTLED = ("done", "cancelled", "failed")


def installed(command: Path, data: Path, package: Path) -> None:
    """The fixture installed under the data directory by the command under test."""
    subprocess.run(
        [str(command), "setup", "openlca", "--data-dir", str(data), "--package", str(package)]
        + ["--name", FIXTURE_DB, "--version", "1"],
        check=True,
        capture_output=True,
    )


async def answer(client: Client, tool: str, **arguments: object) -> dict[str, object]:
    called = await client.call_tool(tool, arguments)
    return called.structured_content or {}


def serving(command: Path, data: Path, systems: Path) -> StdioTransport:
    """A client of the command under test, which starts its server: a new process for each
    transport."""
    return StdioTransport(
        command=str(command),
        args=["serve", "--data-dir", str(data), "--systems-dir", str(systems), "--no-view"],
        env=TELEMETRY_OFF,
    )


async def install_over(client: Client, package: Path) -> dict[str, object]:
    """The fixture's bundle posted as a second database through the tools and followed until it
    is not open."""
    posted = await answer(
        client,
        "install_database",
        source="openlca",
        package=str(package),
        name=INSTALLED,
        version="1",
        system_model="unit process",
        drop_unlinked=True,
    )
    install = posted["value"]
    deadline = time.monotonic() + 120
    while install["open"] and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        install = (await answer(client, "get_install", install_id=str(install["id"])))["value"]
    return install


async def checks(
    command: Path, data: Path, systems: Path, work: Path, package: Path
) -> dict[str, object]:
    started = time.monotonic()
    async with Client(serving(command, data, systems), timeout=120) as client:
        initialized = round(time.monotonic() - started, 2)
        tools = [tool.name for tool in await client.list_tools()]
        made = await answer(client, "create_product_system", name=ACCENTED, database=FIXTURE_DB)
        system = str(made["value"]["id"])
        await answer(
            client,
            "create_process",
            product_system_id=system,
            code="cathode",
            name="cátodo",
            unit="kilogram",
            reference_product="cátodo de cobre",
        )
        await answer(
            client, "update_product_system", product_system_id=system, reference_process="cathode"
        )
        await answer(
            client,
            "create_exchange",
            product_system_id=system,
            code="cathode",
            type="product",
            amount=2.0,
            input={"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]},
            uncertainty={"type": "lognormal", "params": {"loc": 0.6931, "scale": 0.2}},
        )
        exported = work / f"{ACCENTED}.zip"
        await answer(client, "export_product_system", product_system_id=system, path=str(exported))
        await answer(client, "delete_product_system", product_system_id=system)
        back = await answer(client, "import_product_system", path=str(exported))
        read = await answer(client, "get_product_system", product_system_id=system)
        listed = await answer(client, "list_product_systems")
        names = [card["name"] for card in listed["value"]]
        method = (await answer(client, "search_methods", database=FIXTURE_DB, query="gwp"))[
            "items"
        ][0]["id"]
        run = (
            await answer(
                client,
                "start_monte_carlo",
                product_system_id=system,
                method_id=method,
                monte_carlo={"n": 1000, "n_min": 1, "n_max": 1000},
            )
        )["value"]
        await answer(client, "cancel_run", run_id=run["id"])
        deadline = time.monotonic() + 120
        reported = run
        while reported["status"] not in SETTLED and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
            reported = (await answer(client, "get_run", run_id=run["id"]))["value"]
        installing = await install_over(client, package)
        served = await answer(client, "list_databases")
    databases = [database["name"] for database in served["value"]]
    sampled = (reported.get("result") or {}).get("n", 0)
    return {
        "initialize": {"seconds": initialized, "passed": True},
        "tools": {"count": len(tools), "passed": tools == list(ROSTER)},
        "accents": {
            "name": read["value"]["name"],
            "passed": back["value"]["name"] == ACCENTED
            and read["value"]["name"] == ACCENTED
            and ACCENTED in names
            and exported.is_file(),
        },
        "monte_carlo": {
            "status": reported["status"],
            "samples": sampled,
            "passed": reported["status"] == "cancelled" and 0 < sampled < 1000,
        },
        "install": {
            "database": INSTALLED,
            "status": installing["status"],
            "passed": installing["status"] == "done" and INSTALLED in databases,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="end_to_end")
    parser.add_argument("--command", type=Path, default=installed_command())
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        data, systems, sources = work / "data", work / "systems", work / "sources"
        for made in (data, systems, sources):
            made.mkdir()
        package = fixture_bundle(sources)
        installed(args.command, data, package)
        report = asyncio.run(checks(args.command, data, systems, work, package))
    print(json.dumps({"command": str(args.command), **report}, ensure_ascii=False, indent=1))
    return 0 if all(check["passed"] for check in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

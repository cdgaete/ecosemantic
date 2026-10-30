"""The commands: serve the server and its view, write a package, read one back, score a table
folder, set up data, configure a chatbot and report on the install."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from opentelemetry.metrics import MeterProvider
from pydantic import JsonValue

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.cli.accounts import account_for
from ecosemantic.cli.clients import CLIENTS, connect, found
from ecosemantic.cli.doctor import directories, report
from ecosemantic.cli.progress import printer
from ecosemantic.cli.text import (
    Renderer,
    compute_text,
    connect_text,
    database_text,
    doctor_text,
    init_text,
    refusal_text,
    setup_text,
    telemetry_text,
    terms_text,
)
from ecosemantic.compute.links import pinned_documents
from ecosemantic.compute.results import ContributionResult
from ecosemantic.engine.solver import SOLVERS
from ecosemantic.errors import (
    Conflict,
    EcoSemanticError,
    Invalid,
    Remedies,
    StaleScenario,
    Unavailable,
    error_payload,
)
from ecosemantic.installs.sources import install_source
from ecosemantic.local import build_context, default_directories, defaulted
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.treatments import treatments_in
from ecosemantic.model.entities import Actor
from ecosemantic.package.background import Import, read_background
from ecosemantic.package.manifest import BaseDatabase, Manifest, read_manifest
from ecosemantic.package.model_package import export_model_package, import_model_package, stated_at
from ecosemantic.package.release import build_release
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.package.working import (
    build_working,
    foreground_processes,
    restore_systems,
    write_base_part,
)
from ecosemantic.ports.types import (
    InstallDraft,
    InstallProgress,
    InstallTerms,
    InventoryRow,
    Page,
    Reporter,
    SourceName,
    System,
    source_credential,
)
from ecosemantic.settings import TRANSPORTS, ViewSettings, settings_from
from ecosemantic.tables.reader import assemble
from ecosemantic.tables.results import (
    write_contribution,
    write_impact,
    write_inventory,
)
from ecosemantic.telemetry import CHOICES, begin, record, serving, status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ecosemantic", description="EcoSemantic local core.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    def data(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--data-dir", type=Path)

    def answered(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--json", dest="as_json", action="store_true")

    def solved(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--solver", choices=SOLVERS, default="superlu")

    def shared(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = subcommands.add_parser(name, help=help_text)
        data(sub)
        solved(sub)
        sub.add_argument("--systems-dir", type=Path)
        return sub

    serve = shared("serve", "Run the MCP server, with the browser view beside it.")
    serve.add_argument("--transport", choices=TRANSPORTS)
    serve.add_argument("--view-host")
    serve.add_argument("--view-port", type=int)
    serve.add_argument("--view-url")
    serve.add_argument("--token", dest="token", action="store_true", default=None)
    serve.add_argument("--no-token", dest="token", action="store_false", default=None)
    serve.add_argument("--no-view", action="store_true")
    serve.add_argument("--no-open", action="store_true")
    export = shared("export", "Write a stored product system as a portable package.")
    export.add_argument("--id", required=True)
    export.add_argument("--to", required=True, type=Path)
    answered(export)
    importer = shared("import", "Read a package and store the product system it carries.")
    importer.add_argument("--from", dest="source", required=True, type=Path)
    answered(importer)
    compute = subcommands.add_parser(
        "compute", help="Compute a table folder's results, with no store and no server."
    )
    data(compute)
    solved(compute)
    answered(compute)
    compute.add_argument("--folder", required=True, type=Path)
    compute.add_argument("--method")
    compute.add_argument("--impact-method", dest="impact_method")
    compute.add_argument("--variants", default="")
    compute.add_argument("--contributions", action="store_true")
    compute.add_argument("--inventory", action="store_true")
    setup = subcommands.add_parser("setup", help="Install a background database.")
    kinds = setup.add_subparsers(dest="kind", required=True)
    openlca = kinds.add_parser("openlca", help="Install an openLCA JSON-LD package.")
    data(openlca)
    openlca.add_argument("--package", required=True, type=Path)
    openlca.add_argument("--name", required=True)
    openlca.add_argument("--version", required=True)
    openlca.add_argument("--system-model", default="unit process")
    openlca.add_argument("--replace", action="store_true")
    openlca.add_argument("--drop-unlinked", action="store_true")
    answered(openlca)
    uslci = kinds.add_parser("uslci", help="Install the USLCI database a profile pins.")
    data(uslci)
    uslci.add_argument("--version")
    uslci.add_argument("--replace", action="store_true")
    answered(uslci)
    bafu = kinds.add_parser("bafu", help="Install the BAFU database a profile pins.")
    data(bafu)
    bafu.add_argument("--version")
    bafu.add_argument("--replace", action="store_true")
    bafu.add_argument("--accept-terms", dest="accept_terms", action="store_true")
    answered(bafu)
    ecoinvent = kinds.add_parser("ecoinvent", help="Install an ecoinvent release it builds.")
    data(ecoinvent)
    answered(ecoinvent)
    ecoinvent.add_argument("version", help="The release to install, as a profile names it.")
    ecoinvent.add_argument("--system-model", default="cutoff")
    ecoinvent.add_argument("--replace", action="store_true")
    database = subcommands.add_parser("database", help="Save, release or load a database bundle.")
    actions = database.add_subparsers(dest="action", required=True)
    for action, text in (
        ("save", "Write every stored system whole beside the base it reaches."),
        ("release", "Render every stored system's cases to numbers beside the base it reaches."),
    ):
        builder = actions.add_parser(action, help=text)
        data(builder)
        builder.add_argument("--systems-dir", type=Path)
        builder.add_argument("--base", required=True)
        builder.add_argument("--name", required=True)
        builder.add_argument("--version", required=True)
        builder.add_argument("--to", required=True, type=Path)
        if action == "release":
            builder.add_argument("--previous", type=Path)
        answered(builder)
    loader = actions.add_parser("load", help="Install a database bundle and restore its systems.")
    data(loader)
    loader.add_argument("--systems-dir", type=Path)
    loader.add_argument("--from", dest="source", required=True, type=Path)
    answered(loader)
    connecting = subcommands.add_parser(
        "connect", help="Write this server into a chatbot's MCP configuration."
    )
    connecting.add_argument("client", choices=CLIENTS)
    connecting.add_argument("--workspace", type=Path)
    connecting.add_argument("--command", dest="command_path", type=Path)
    answered(connecting)
    doctor = subcommands.add_parser("doctor", help="Report what this install holds and lacks.")
    doctor.add_argument("--data-dir", dest="data", type=Path)
    doctor.add_argument("--systems-dir", dest="systems", type=Path)
    answered(doctor)
    telemetry = subcommands.add_parser(
        "telemetry", help="Show or set whether this install counts server starts and tool calls."
    )
    telemetry.add_argument("choice", nargs="?", choices=CHOICES)
    telemetry.add_argument("--data-dir", dest="data", type=Path)
    answered(telemetry)
    initializing = subcommands.add_parser(
        "init", help="Connect the chatbots found and say what comes next."
    )
    initializing.add_argument("--client", dest="clients", action="append", choices=CLIENTS)
    answered(initializing)
    return parser


def _defaulted(args: argparse.Namespace) -> None:
    """Give a command that names no data directory, or no product systems directory, this
    platform's default for the one it lacks."""
    lacking = [name for name in ("data_dir", "systems_dir") if getattr(args, name, False) is None]
    if lacking:
        defaults = dict(zip(("data_dir", "systems_dir"), default_directories(), strict=True))
        for name in lacking:
            setattr(args, name, defaulted(None, defaults[name]))


async def _compute(args: argparse.Namespace, progress: Reporter) -> dict[str, object]:
    """Score a folder's document against the named method and write one run folder."""
    from ecosemantic.mcp.calculation import impact_of, methods_for
    from ecosemantic.mcp.tables import result_key

    if not args.folder.is_dir():
        raise Invalid(f"{str(args.folder)!r} is not a directory")
    system = assemble(args.folder)
    store = NativeStore(args.data_dir, args.solver)
    try:
        progress(InstallProgress(step="scoring"))
        inventory = NativeInventory(store)
        calculation = NativeCalculation(store)
        methods, _ = await methods_for(
            inventory, system.database.name, args.method, args.impact_method
        )
        names = [name for name in args.variants.split(",") if name]
        scored = System.of(system)
        treatments = await treatments_in(inventory, [system])
        result = await impact_of(
            calculation, system, methods, variants=names, treatments=treatments
        )
        key = result_key(system, args.method, args.impact_method, None, names)
        items = key.demand
        at = datetime.now(UTC)
        progress(InstallProgress(step="writing"))
        written = [str(write_impact(args.folder, key, result, at))]
        if args.contributions:
            hotspots = await calculation.hotspots(scored, items, methods[0])
            decomposed = ContributionResult(
                database=system.database,
                by="process",
                total=hotspots.total,
                processes=hotspots.items,
                credit_loops=result.credit_loops,
                linked_credit_loops=result.linked_credit_loops,
                treatments_run_backwards=result.treatments_run_backwards,
            )
            written.append(str(write_contribution(args.folder, key, decomposed, at)))
        if args.inventory:
            found = await calculation.inventory(scored, items)
            page = Page[InventoryRow](items=found.rows, has_more=False)
            written.append(
                str(
                    write_inventory(
                        args.folder,
                        key,
                        system.database,
                        page,
                        result.credit_loops,
                        result.linked_credit_loops,
                        result.treatments_run_backwards,
                        at,
                    )
                )
            )
    finally:
        store.close()
    return {"folder": written[0], "written": written, "hash": key.hash, "method": key.method}


def _setup(args: argparse.Namespace, progress: Reporter) -> dict[str, JsonValue] | InstallTerms:
    """Install a background database: an openLCA package, or a source this package builds."""
    package = getattr(args, "package", None)
    draft = InstallDraft(
        source=cast(SourceName, args.kind),
        actor=Actor(kind="person", name="command line"),
        version=getattr(args, "version", None),
        system_model=getattr(args, "system_model", None),
        replace=getattr(args, "replace", False),
        accept_terms=getattr(args, "accept_terms", False),
        package=None if package is None else str(package),
        name=getattr(args, "name", None),
        drop_unlinked=getattr(args, "drop_unlinked", False),
    )
    kind = source_credential(draft.source)
    account = None if kind is None else account_for(kind, os.environ, sys.stdin.isatty())
    return install_source(args.data_dir, draft, account, progress)


def serve_offline() -> None:
    """Keep the stdio server's own network use to EcoSemantic's counts, when telemetry is on: no
    update check against PyPI and no FastMCP tracing."""
    import fastmcp

    fastmcp.settings.check_for_updates = "off"
    fastmcp.settings.telemetry_mode = "off"


async def run(
    context: ServerContext,
    settings: ViewSettings,
    systems_dir: Path,
    meter_provider: MeterProvider | None = None,
) -> None:
    """Serve under these settings, loading the process that serves here so no other command
    loads the server or the page."""
    from ecosemantic.serve import run as serving

    await serving(context, settings, systems_dir, meter_provider=meter_provider)


def _context(args: argparse.Namespace) -> ServerContext:
    return build_context(
        args.data_dir,
        args.systems_dir,
        agent=os.environ.get("ECOSEMANTIC_AGENT"),
        solver=args.solver,
    )


def _export(context: ServerContext, product_system_id: str, target: Path) -> None:
    from ecosemantic.mcp.envelopes import as_uuid

    system = asyncio.run(context.storage.get_product_system(as_uuid(product_system_id)))
    linked = asyncio.run(pinned_documents(system, context.storage.get_version))
    at = stated_at(system, asyncio.run(context.storage.log(system.id)))
    export_model_package(system, target, context.actor, context.resolver, linked=linked, at=at)


def _import(context: ServerContext, source: Path) -> None:
    asyncio.run(import_model_package(source, context.storage, context.actor))


REMEDIES: Remedies = {
    StaleScenario: (
        "a folder applies a scenario only at the inputs it was exported with: restore them, or "
        "store the inputs with import_tables, rebase the scenario and export the folder again"
    )
}


def _refused(exc: EcoSemanticError, as_json: bool) -> int:
    """Name the refusal on standard error: the error line under `--json`, the message and its
    hint otherwise."""
    envelope = error_payload(exc, REMEDIES)
    print(envelope.model_dump_json() if as_json else refusal_text(envelope), file=sys.stderr)
    return 1


def _answered(answer: Mapping[str, object], as_json: bool, render: Renderer) -> None:
    """Print a command's answer: the JSON object main prints under `--json`, and the text the
    renderer builds otherwise."""
    print(json.dumps(_printed(answer)) if as_json else render(answer))


def _printed(answer: object) -> object:
    """A command's answer as the one JSON document main prints: the terms of a source to accept, and
    any other answer as it stands."""
    if isinstance(answer, InstallTerms):
        return {"licence": answer.licence, "citation": answer.citation}
    return answer


def _code(answer: object) -> int:
    """2 for the answer that asks for a source's terms to be accepted, and 0 for one that stands."""
    return 2 if isinstance(answer, InstallTerms) else 0


ALL = "all"
NO_CHATBOT = "no chatbot is installed"
INSTALL_CHATBOT = (
    "install Claude Desktop from https://claude.ai/download, then run: ecosemantic init"
)
NEXT = "Restart your chatbot; the EcoSemantic page opens in your browser."


def _choice(answer: str, clients: list[str]) -> list[str] | None:
    """The chatbots one answer names: one of them by its number, and every one of them for `all`;
    None for an answer that names neither."""
    text = answer.strip().lower()
    if text == ALL:
        return clients
    numbered = {str(number): client for number, client in enumerate(clients, start=1)}
    if text in numbered:
        return [numbered[text]]
    return None


def _asked(clients: list[str]) -> list[str]:
    """The chatbots the person picks at a terminal: the ones a number names, or all of them,
    asked again until the answer names one of the choices."""
    question = "\n".join(
        [
            *(f"{number}. {client}" for number, client in enumerate(clients, start=1)),
            f"{len(clients) + 1}. {ALL}",
            "Which chatbots should I connect?",
        ]
    )
    chosen: list[str] | None = None
    while chosen is None:
        print(question, file=sys.stderr)
        chosen = _choice(input(), clients)
    return chosen


def _init(args: argparse.Namespace) -> dict[str, object]:
    """Connect every chatbot the person names, or every one this platform holds, asking which of
    them at a terminal when it holds several; answer with the ones connected, the install as it
    now stands and the step that comes next."""
    clients = list(args.clients) if args.clients else found()
    if not clients:
        raise Unavailable(NO_CHATBOT, INSTALL_CHATBOT)
    if args.clients is None and len(clients) > 1 and sys.stdin.isatty():
        clients = _asked(clients)
    data, systems = directories(None, None)
    return {
        "connected": [connect(client, None, None) for client in clients],
        "doctor": report(data, systems, _databases(data)),
        "next": NEXT,
    }


def _databases(data: Path) -> object:
    """The names of the databases a data directory holds, none when it does not exist, or the
    error its registry answers."""
    if not data.is_dir():
        return []
    try:
        store = NativeStore(data)
    except EcoSemanticError as exc:
        return error_payload(exc).model_dump(mode="json")
    try:
        return [database.name for database in store.databases()]
    finally:
        store.close()


def _parts(data: Path, systems: Path) -> tuple[NativeStore, FilesystemStorage, InventoryResolver]:
    store = NativeStore(data)
    resolver = InventoryResolver(NativeInventory(store))
    return store, FilesystemStorage(systems, resolver), resolver


def _held(data: Path, manifest: Manifest, imported: Import) -> bool:
    """Whether the data directory holds a working bundle's base: Conflict for another version
    of it, for one that lacks a process the bundle carries, or for another build of it than the
    one the bundle's systems were stamped with."""
    store = NativeStore(data)
    try:
        if manifest.base.name not in {d.name for d in store.databases()}:
            return False
        version = store.registered(manifest.base.name).database.version
        if version != manifest.base.version:
            raise Conflict(
                f"{manifest.base.name!r} is held at version {version!r}; the bundle was built "
                f"on version {manifest.base.version!r}"
            )
        lacking = {code for _, code in imported.datasets} - store.native_ids(manifest.base.name)
        if lacking:
            raise Conflict(
                f"{manifest.base.name!r} lacks {len(lacking)} processes the bundle carries"
            )
        held = store.registered(manifest.base.name).database.fingerprint
        built_on = manifest.base.fingerprint
        if built_on is not None and held != built_on:
            raise Conflict(
                f"{manifest.base.name!r} is held at build {str(held)[:12]}; the bundle was built "
                f"on build {built_on[:12]}"
            )
        return True
    finally:
        store.close()


def _load(data: Path, systems: Path, bundle: Path, progress: Reporter) -> dict[str, object]:
    progress(InstallProgress(step="reading"))
    manifest = read_manifest(bundle)
    if manifest.mode == "release":
        imported = read_background(bundle, manifest.name, foreground=frozenset())
        progress(InstallProgress(step="installing"))
        install(data, imported, bundle, version=manifest.version, system_model="unit process")
        return {"database": manifest.name, "datasets": len(imported.datasets)}
    imported = read_background(bundle, manifest.base.name, foreground=foreground_processes(bundle))
    base = "kept"
    if not _held(data, manifest, imported):
        with tempfile.TemporaryDirectory() as work:
            part = Path(work) / f"{manifest.base.name}.zip"
            write_base_part(bundle, part)
            progress(InstallProgress(step="installing"))
            install(
                data,
                read_background(part, manifest.base.name, foreground=frozenset()),
                part,
                version=manifest.base.version,
                system_model="unit process",
            )
        base = "installed"
    store, storage, resolver = _parts(data, systems)
    try:
        restored = asyncio.run(restore_systems(bundle, storage))
    finally:
        resolver.close()
        store.close()
    return {"base": base, "systems": {str(k): v for k, v in restored.items()}}


def _build(args: argparse.Namespace) -> dict[str, object]:
    store, storage, resolver = _parts(args.data_dir, args.systems_dir)
    try:
        held = store.registered(args.base).database
        base = BaseDatabase(name=held.name, version=held.version, fingerprint=held.fingerprint)
        bundle = store.bundle_of(args.base)
        now = datetime.now(UTC)
        if args.action == "save":
            manifest = asyncio.run(
                build_working(storage, bundle, base, args.name, args.version, args.to, now)
            )
        else:
            manifest = asyncio.run(
                build_release(
                    storage, bundle, base, args.name, args.version, args.to, args.previous, now
                )
            )
    finally:
        resolver.close()
        store.close()
    return {
        "bundle": str(args.to),
        "mode": manifest.mode,
        "systems": len(manifest.systems),
        "datasets": len(manifest.datasets),
    }


def _database(args: argparse.Namespace, progress: Reporter) -> dict[str, object]:
    if args.action == "load":
        return _load(args.data_dir, args.systems_dir, args.source, progress)
    return _build(args)


def main(argv: list[str] | None = None) -> int:
    """Run one command; 0 on success, 1 on a typed error, 2 on a usage error or a source whose
    terms are not accepted."""
    parser = _parser()
    if argv is not None and not argv:
        parser.print_usage(sys.stderr)
        print(
            "a subcommand is required: serve, export, import, compute, setup, database, "
            "connect, doctor, init, telemetry",
            file=sys.stderr,
        )
        return 2
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "as_json", False))
    progress = printer(sys.stderr, time.monotonic())
    try:
        _defaulted(args)
    except EcoSemanticError as exc:
        return _refused(exc, as_json)
    if args.command in ("connect", "doctor", "init", "telemetry"):
        try:
            if args.command == "connect":
                answered = connect(args.client, args.workspace, args.command_path)
                _answered(answered, as_json, connect_text)
            elif args.command == "init":
                answered = _init(args)
                _answered(answered, as_json, init_text)
            elif args.command == "telemetry":
                data = directories(args.data, None)[0]
                if args.choice is not None:
                    record(os.environ, data, args.choice == "on")
                _answered(status(os.environ, data), as_json, telemetry_text)
            else:
                data, systems = directories(args.data, args.systems)
                answered = report(data, systems, _databases(data))
                _answered(answered, as_json, doctor_text)
        except EcoSemanticError as exc:
            return _refused(exc, as_json)
        return 0
    if args.command in ("setup", "database"):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                summary = (
                    _setup(args, progress) if args.command == "setup" else _database(args, progress)
                )
            if isinstance(summary, InstallTerms):
                if as_json:
                    print(json.dumps(_printed(summary)))
                else:
                    print(terms_text(summary.licence, summary.citation))
            elif args.command == "setup":
                _answered(summary, as_json, setup_text)
            else:
                _answered(summary, as_json, database_text)
        except EcoSemanticError as exc:
            return _refused(exc, as_json)
        return _code(summary)
    if args.command == "compute":
        try:
            with contextlib.redirect_stdout(sys.stderr):
                answered = asyncio.run(_compute(args, progress))
            _answered(answered, as_json, compute_text)
        except EcoSemanticError as exc:
            return _refused(exc, as_json)
        return 0
    try:
        with contextlib.redirect_stdout(sys.stderr):
            context = _context(args)
    except EcoSemanticError as exc:
        return _refused(exc, as_json)
    try:
        if args.command == "serve":
            serve_offline()
            logging.basicConfig(stream=sys.stderr, level=logging.INFO)
            settings = settings_from(
                os.environ,
                args.systems_dir,
                enabled=False if args.no_view else None,
                host=args.view_host,
                port=args.view_port,
                url=args.view_url,
                transport=args.transport,
                token=args.token,
                opening=False if args.no_open else None,
            )
            provider = begin(os.environ, args.data_dir, settings.transport, sys.stderr)
            with serving(provider):
                asyncio.run(run(context, settings, args.systems_dir, meter_provider=provider))
        elif args.command == "export":
            _export(context, args.id, args.to)
        else:
            _import(context, args.source)
    except EcoSemanticError as exc:
        return _refused(exc, as_json)
    finally:
        context.close()
    return 0

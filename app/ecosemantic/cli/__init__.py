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
import webbrowser
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import cast

from opentelemetry.metrics import MeterProvider
from pydantic import JsonValue

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.bridge.credentials import (
    NO_STORE_HINT,
    Credential,
    CredentialStore,
    engine_token,
    has_credential_store,
    store_for,
    token_variable,
)
from ecosemantic.bridge.signin import CREDENTIAL_KEPT, client, discover, sign_in, sign_out
from ecosemantic.bridge.start import (
    DEFAULT_BRIDGE_URL,
    BridgeStart,
    bridge_start,
    engine_name,
    engine_version,
)
from ecosemantic.cli.accounts import account_for
from ecosemantic.cli.clients import CLIENTS, connect, found
from ecosemantic.cli.doctor import directories, report
from ecosemantic.cli.progress import printer
from ecosemantic.cli.text import (
    Renderer,
    bridge_sign_in_text,
    bridge_sign_out_text,
    bridge_status_text,
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
from ecosemantic.engine.solver import SOLVERS
from ecosemantic.errors import (
    Conflict,
    EcoSemanticError,
    Invalid,
    Remedies,
    StaleScenario,
    Unauthorised,
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
from ecosemantic.package.model_package import import_model_package
from ecosemantic.package.release import build_release
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.package.working import (
    build_working,
    foreground_processes,
    restore_systems,
    write_base_part,
)
from ecosemantic.ports.types import (
    UNIT_PROCESS,
    InstallDraft,
    InstallProgress,
    InstallTerms,
    InventoryRow,
    Page,
    Reporter,
    SourceName,
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
        sub.add_argument(
            "--data-dir", type=Path, help="The directory the databases are installed in."
        )

    def answered(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--json",
            dest="as_json",
            action="store_true",
            help="Print the answer as one JSON document.",
        )

    def solved(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--solver",
            choices=SOLVERS,
            default="superlu",
            help="The solver a calculation runs on.",
        )

    def shared(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = subcommands.add_parser(name, help=help_text)
        data(sub)
        solved(sub)
        sub.add_argument(
            "--systems-dir", type=Path, help="The directory the product systems are kept in."
        )
        return sub

    serve = shared("serve", "Run the MCP server, with the browser view beside it.")
    serve.add_argument(
        "--transport", choices=TRANSPORTS, help="Serve over stdio or over the page's listener."
    )
    serve.add_argument("--view-host", help="The host the page's listener binds.")
    serve.add_argument("--view-port", type=int, help="The port the page's listener binds.")
    serve.add_argument("--view-url", help="The address the server announces to chats.")
    serve.add_argument(
        "--token",
        dest="token",
        action="store_true",
        default=None,
        help="Require the workspace's token on the page's requests.",
    )
    serve.add_argument(
        "--no-token",
        dest="token",
        action="store_false",
        default=None,
        help="Admit the page's requests without a token.",
    )
    serve.add_argument("--no-view", action="store_true", help="Serve with no page.")
    serve.add_argument("--no-open", action="store_true", help="Do not open the page in a browser.")
    serve.add_argument(
        "--bridge",
        action="store_true",
        default=None,
        help="Serve this engine to chats through the bridge.",
    )
    serve.add_argument("--bridge-url", help="The bridge this engine connects to.")
    serve.add_argument(
        "--credential-file",
        dest="credential_file",
        type=Path,
        help="The file the bridge's credential is kept in.",
    )
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
    openlca.add_argument("--system-model", default=UNIT_PROCESS)
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
    bridge = subcommands.add_parser(
        "bridge", help="Sign this engine in to the bridge, out of it, or report it."
    )
    verbs = bridge.add_subparsers(dest="action", required=True)

    def bridged(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--bridge-url", help="The bridge this engine connects to.")
        sub.add_argument(
            "--credential-file",
            dest="credential_file",
            type=Path,
            help="The file the bridge's credential is kept in.",
        )
        sub.add_argument(
            "--systems-dir", type=Path, help="The directory the product systems are kept in."
        )

    signing = verbs.add_parser("sign-in", help="Sign this engine in to the bridge.")
    bridged(signing)
    signing.add_argument(
        "--device", action="store_true", help="Sign in with the device flow, without a browser."
    )
    signing.add_argument("--name", help="The name this engine registers with the bridge.")
    answered(signing)
    signing.set_defaults(handler=_signed_in, renderer=bridge_sign_in_text)
    signing_out = verbs.add_parser("sign-out", help="Sign this engine out of the bridge.")
    bridged(signing_out)
    answered(signing_out)
    signing_out.set_defaults(
        handler=_signed_out, renderer=bridge_sign_out_text, remedy=CREDENTIAL_KEPT
    )
    reporting = verbs.add_parser("status", help="Report whether this engine is signed in.")
    bridged(reporting)
    answered(reporting)
    reporting.set_defaults(handler=_status, renderer=bridge_status_text)
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


def _bridge_url(named: str | None, environ: Mapping[str, str]) -> str:
    """The bridge a command works with: the address it names, the variable standing in for it, or
    the bridge's own default address."""
    if named is not None:
        return named
    return environ.get("ECOSEMANTIC_BRIDGE_URL", DEFAULT_BRIDGE_URL)


def _credential_file(named: Path | None, environ: Mapping[str, str]) -> Path | None:
    """The file the credential is kept in, when the command or its variable names one."""
    if named is not None:
        return named
    held = environ.get("ECOSEMANTIC_BRIDGE_CREDENTIAL_FILE")
    return None if held is None else Path(held)


def _shown(code: str, address: str) -> None:
    """Show a device sign-in's code and the address the person enters it at."""
    print(f"code: {code}\naddress: {address}", file=sys.stderr, flush=True)


def _browser(url: str) -> None:
    """Show a sign-in's address in this machine's default browser."""
    webbrowser.open(url)


def _bridge(args: argparse.Namespace) -> tuple[dict[str, object], Renderer]:
    """Answer the bridge command the parsed verb bound, and name the renderer it bound with it."""
    handler: Callable[[argparse.Namespace], dict[str, object]] = args.handler
    return handler(args), args.renderer


def _status(args: argparse.Namespace) -> dict[str, object]:
    """Whether this engine is signed in to the bridge, from the store and the engine token's
    variables alone: the handle, the page address and the engine it serves, and where the
    credential is kept; a machine with no credential store names that and the ways that need
    none."""
    environ = os.environ
    if engine_token(environ) is not None:
        return {"signed_in": True, "where": token_variable(environ)}
    credential_file = _credential_file(args.credential_file, environ)
    if credential_file is None and not has_credential_store():
        return {"signed_in": False, "where": None, "hint": NO_STORE_HINT}
    store = store_for(_bridge_url(args.bridge_url, environ), args.systems_dir, credential_file)
    credential = store.load()
    if credential is None:
        return {"signed_in": False, "where": store.where}
    return {
        "signed_in": True,
        "handle": credential.handle,
        "page": credential.page_url,
        "engine": str(credential.engine),
        "where": store.where,
    }


def _signed_in(args: argparse.Namespace) -> dict[str, object]:
    """Sign this systems directory's engine in to the bridge, through the browser or the device
    flow, and answer the connector address, the page address and where the credential is kept."""
    return asyncio.run(_signing_in(args))


async def _signing_in(args: argparse.Namespace) -> dict[str, object]:
    """The sign-in itself: the bridge's discovery document, the sign-in it grants, and the
    registration it answers with the engine's handle and page address."""
    from ecosemantic.serve import browser_reachable

    environ = os.environ
    url = _bridge_url(args.bridge_url, environ)
    store = store_for(url, args.systems_dir, _credential_file(args.credential_file, environ))
    async with client() as http:
        config = await discover(http, url)
        credential = await sign_in(
            http,
            url,
            store,
            args.device or not browser_reachable(environ, sys.platform),
            args.name or engine_name(),
            engine_version(),
            _browser,
            _shown,
        )
    return {
        "connector": config.connector_url,
        "page": credential.page_url,
        "where": store.where,
    }


def _signed_out(args: argparse.Namespace) -> dict[str, object]:
    """Sign this systems directory out of the bridge, refusing while an engine token gives it its
    sign-in: the bridge and the engine whose grant was revoked, or that nothing was stored, a
    machine with no credential store having nothing to revoke."""
    environ = os.environ
    variable = token_variable(environ)
    if variable is not None and engine_token(environ) is not None:
        raise Invalid(
            f"{variable} names an engine token, which is revoked on the bridge's account page"
        )
    url = _bridge_url(args.bridge_url, environ)
    credential_file = _credential_file(args.credential_file, environ)
    if credential_file is None and not has_credential_store():
        return {"signed_out": False, "bridge": url, "where": None}
    store = store_for(url, args.systems_dir, credential_file)
    revoked = asyncio.run(_signing_out(store))
    if revoked is None:
        return {"signed_out": False, "bridge": url, "where": store.where}
    return {
        "signed_out": True,
        "bridge": url,
        "engine": str(revoked.engine),
        "where": store.where,
    }


async def _signing_out(store: CredentialStore) -> Credential | None:
    """The revocation the bridge's Logto answers for the credential this store holds, and the
    credential it revoked, or None when the store holds none."""
    async with client() as http:
        return await sign_out(http, store)


async def _compute(args: argparse.Namespace, progress: Reporter) -> dict[str, object]:
    """Score a folder's document against the named method and write one run folder."""
    from ecosemantic.mcp.calculation import contributions_of, impact_of, inventory_of, methods_for
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
            decomposed = await contributions_of(
                calculation, treatments, system, {}, methods[0], items
            )
            written.append(str(write_contribution(args.folder, key, decomposed, at)))
        if args.inventory:
            counted, rows = await inventory_of(calculation, treatments, system, {}, items)
            page = Page[InventoryRow](items=rows, has_more=False)
            written.append(str(write_inventory(args.folder, key, counted, page, at)))
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
    bridge: BridgeStart | None = None,
) -> None:
    """Serve under these settings through the process that serves, which `_serving` loads."""
    await _serving().run(
        context, settings, systems_dir, meter_provider=meter_provider, bridge=bridge
    )


async def _serve(
    context: ServerContext,
    settings: ViewSettings,
    args: argparse.Namespace,
    meter_provider: MeterProvider | None,
) -> None:
    """Serve, having started the bridge first when the server was told to: its engine token, its
    stored credential or a sign-in, and the page address and proof the listener is built on."""
    if not settings.bridge:
        await run(context, settings, args.systems_dir, meter_provider=meter_provider)
        return
    bridge = await bridge_start(
        _bridge_url(args.bridge_url, os.environ),
        args.systems_dir,
        _credential_file(args.credential_file, os.environ),
        os.environ,
        sys.stdin.isatty(),
        _browser,
        _shown,
    )
    await run(context, settings, args.systems_dir, meter_provider=meter_provider, bridge=bridge)


def _serving() -> ModuleType:
    """The process that serves here, loaded on first use so no other command loads the server or
    the page, and loaded where a library's print goes to stderr rather than to the wire."""
    from ecosemantic import serve

    return serve


def _context(args: argparse.Namespace) -> ServerContext:
    return build_context(
        args.data_dir,
        args.systems_dir,
        agent=os.environ.get("ECOSEMANTIC_AGENT"),
        solver=args.solver,
    )


def _export(context: ServerContext, product_system_id: str, target: Path) -> None:
    from ecosemantic.mcp.systems import export_product_system

    asyncio.run(export_product_system(context, product_system_id, str(target)))


def _import(context: ServerContext, source: Path) -> None:
    asyncio.run(import_model_package(source, context.storage, context.actor))


REMEDIES: Remedies = {
    StaleScenario: (
        "a folder applies a scenario only at the inputs it was exported with: restore them, or "
        "store the inputs with import_tables, rebase the scenario and export the folder again"
    )
}


def _refused(exc: EcoSemanticError, as_json: bool, remedy: str | None = None) -> int:
    """Name the refusal on standard error: the error line under `--json`, the message and its
    hint otherwise. A verb that names what its caller does next about a refusal it cannot act on
    binds that remedy, and it answers as the hint of the refusal that carries none."""
    if remedy is not None:
        if isinstance(exc, Unavailable):
            exc = Unavailable(str(exc), hint=exc.hint or remedy)
        elif isinstance(exc, Unauthorised):
            exc = Unauthorised(str(exc), hint=exc.hint or remedy)
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
        install(data, imported, bundle, version=manifest.version, system_model=UNIT_PROCESS)
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
                system_model=UNIT_PROCESS,
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
            "a subcommand is required: serve, export, import, compute, setup, database, bridge, "
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
    if args.command in ("bridge", "connect", "doctor", "init", "telemetry"):
        try:
            if args.command == "connect":
                answered = connect(args.client, args.workspace, args.command_path)
                _answered(answered, as_json, connect_text)
            elif args.command == "bridge":
                answered, render = _bridge(args)
                _answered(answered, as_json, render)
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
            return _refused(exc, as_json, getattr(args, "remedy", None))
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
            with contextlib.redirect_stdout(sys.stderr):
                serve_offline()
                _serving()
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
                bridge=args.bridge,
                bridge_url=args.bridge_url,
                credential_file=args.credential_file,
            )
            provider = begin(os.environ, args.data_dir, settings.transport, sys.stderr)
            with serving(provider):
                asyncio.run(_serve(context, settings, args, provider))
        elif args.command == "export":
            _export(context, args.id, args.to)
        else:
            _import(context, args.source)
    except EcoSemanticError as exc:
        return _refused(exc, as_json)
    finally:
        context.close()
    return 0

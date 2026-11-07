"""The text a command prints on standard output, and the text a refusal prints on standard error:
what was done, the numbers that matter and the step that comes next."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from ecosemantic.errors import ErrorEnvelope
from ecosemantic.telemetry import DO_NOT_TRACK, NOTICE, SWITCH

Renderer = Callable[[Mapping[str, object]], str]

INSTALL = "install one from the page, or run: ecosemantic setup uslci"
FIRST_START = "the server makes it on its first start"
PARDISO = 'install "ecosemantic[mkl]" for PARDISO on Linux and Windows x86-64'
NOTHING_REVOKED = "this systems directory is not signed in to the bridge; nothing was revoked"
BRIDGE_RENEWAL = (
    "a server serving this systems directory stops its bridge at its next token renewal"
)


def _map(value: object) -> Mapping[str, object]:
    """One section of a report or an answer, as `report` and the commands build it."""
    return cast("Mapping[str, object]", value)


def _row(label: str, value: object) -> str:
    return f"  {label:<12} {value}"


def setup_text(summary: Mapping[str, object]) -> str:
    """What one install wrote — the database, its processes, datasets, flows and methods, the
    inputs it cut off and the directory holding it — and the step that comes next."""
    database = summary["database"]
    return "\n".join(
        [
            f"installed {database}",
            _row("processes", summary["processes"]),
            _row("datasets", summary["datasets"]),
            _row("flows", summary["flows"]),
            _row("methods", summary["methods"]),
            _row("cut off", len(cast(list[object], summary["cut_off"]))),
            _row("directory", summary["directory"]),
            f"Ask your chatbot for a model on {database}.",
        ]
    )


def terms_text(licence: str | Path, citation: str) -> str:
    """The licence file to read and the release's citation, and the flag that accepts them."""
    return "\n".join(
        [
            _row("citation", citation),
            _row("licence", licence),
            "Run the command again with --accept-terms to accept them.",
        ]
    )


def database_text(answer: Mapping[str, object]) -> str:
    """What a database command wrote or loaded: a bundle with its mode and counts, a release
    database with its datasets, or a working load with its base and each system's state."""
    if "bundle" in answer:
        return "\n".join(
            [
                f"wrote {answer['bundle']}",
                _row("mode", answer["mode"]),
                _row("systems", answer["systems"]),
                _row("datasets", answer["datasets"]),
            ]
        )
    if "database" in answer:
        return "\n".join([f"loaded {answer['database']}", _row("datasets", answer["datasets"])])
    systems = _map(answer["systems"])
    return "\n".join(
        [f"loaded the bundle, base {answer['base']}"]
        + [_row(str(state), system) for system, state in systems.items()]
    )


def bridge_sign_in_text(answer: Mapping[str, object]) -> str:
    """The connector address to add in a chat, the page address the engine answers at, and where
    the credential is kept."""
    return "\n".join(
        [
            f"add {answer['connector']} as a connector in your chat",
            _row("page", answer["page"]),
            _row("kept in", answer["where"]),
        ]
    )


def bridge_sign_out_text(answer: Mapping[str, object]) -> str:
    """What a sign-out did: the bridge whose grant it revoked and the engine it named, the store
    the credential was revoked from with the renewal that stops a server serving this systems
    directory; or that the store held no credential to revoke."""
    if not answer["signed_out"]:
        return NOTHING_REVOKED
    return "\n".join(
        [
            f"signed out of {answer['bridge']}",
            _row("engine", answer["engine"]),
            _row("revoked", f"the credential in {answer['where']}"),
            BRIDGE_RENEWAL,
        ]
    )


def bridge_status_text(answer: Mapping[str, object]) -> str:
    """Whether this engine is signed in: its handle, page address and engine id with the store
    that keeps its credential, the engine token's variable, the sign-in that comes next, or the
    machine having no credential store with the two ways that need none."""
    if not answer["signed_in"]:
        if "hint" in answer:
            return f"not signed in; this machine has no credential store: {answer['hint']}"
        return "\n".join(
            [
                "not signed in to the bridge",
                _row("run", "ecosemantic bridge sign-in"),
                _row("kept in", answer["where"]),
            ]
        )
    if "handle" not in answer:
        return "\n".join(
            [
                "signed in through the engine token",
                _row("variable", answer["where"]),
            ]
        )
    return "\n".join(
        [
            f"signed in as {answer['handle']}",
            _row("page", answer["page"]),
            _row("engine", answer["engine"]),
            _row("kept in", answer["where"]),
        ]
    )


def compute_text(answer: Mapping[str, object]) -> str:
    """Where a compute wrote its run folder, the method and hash it scored, and each table it
    wrote beside the folder."""
    written = cast("list[str]", answer["written"])
    return "\n".join(
        [
            f"wrote {answer['folder']}",
            _row("method", answer["method"]),
            _row("hash", answer["hash"]),
            _row("files", len(written)),
            *(f"  {path}" for path in written),
        ]
    )


def connect_text(answer: Mapping[str, object]) -> str:
    """Where a chatbot's configuration gained this server, the command it starts and whether an
    entry of the same name was replaced."""
    state = "replaced the server entry" if answer["replaced"] else "added the server entry"
    return "\n".join(
        [
            f"{state} in {answer['path']}",
            _row("client", answer["client"]),
            _row("server", answer["server"]),
            _row("command", answer["command"]),
        ]
    )


def _directory_row(name: str, directory: Mapping[str, object]) -> str:
    state = "" if directory["exists"] else f", missing: {FIRST_START}"
    return _row(name, f"{directory['path']}{state}")


def _database_rows(databases: object) -> list[str]:
    if isinstance(databases, list) and databases:
        return [_row("installed", name) for name in databases]
    if isinstance(databases, list):
        return [_row("none", INSTALL)]
    return [_row("unreadable", databases)]


def _page_rows(page: Mapping[str, object]) -> list[str]:
    """The page's address and whether its port is free, or the message of a setting the install
    cannot use."""
    if "error" in page:
        return [_row("error", page["error"])]
    free = "" if page["free"] else ", the port is in use"
    return [_row("address", f"{page['host']}:{page['port']}{free}")]


def _client_row(client: str, answered: Mapping[str, object]) -> str:
    connect = f"run: ecosemantic connect {client}"
    if "documented" in answered:
        return _row(client, f"no documented location ({answered['message']}): {connect}")
    where = answered["path"]
    if "error" in answered:
        return _row(client, f"{where}: {answered['error']}; {connect} once it reads")
    if not answered["present"]:
        return _row(client, f"{where}: no server entry, {connect}")
    if not answered["command_exists"]:
        return _row(client, f"{where}: its command is not installed, {connect}")
    return _row(client, f"{where}: configured")


def _telemetry_rows(held: Mapping[str, object]) -> list[str]:
    if "error" in held:
        return [_row("error", held["error"])]
    rows = [
        _row("telemetry", f"{'on' if held['on'] else 'off'} ({held['reason']})"),
        _row("identifier", held["install_id"] or "none yet"),
        _row("endpoint", held["endpoint"]),
    ]
    if held["reason"] in (SWITCH, DO_NOT_TRACK):
        rows.append(
            _row(
                "applies to",
                f"servers started with this environment; a chatbot starts its server with its "
                f"own, without {held['reason']}. `ecosemantic telemetry off` turns telemetry off "
                "for every server on this machine that no variable decides for.",
            )
        )
    if held["on"]:
        rows.append(f"  {NOTICE}")
    return rows


def telemetry_text(answer: Mapping[str, object]) -> str:
    """Whether telemetry is on and what decided it, the identifier kept, the endpoint and the file
    that holds the choice, and that a choice applies to servers started after it. A variable that
    decides is said to reach only servers started with this environment."""
    return "\n".join(
        [
            *_telemetry_rows(answer),
            _row("file", answer["file"]),
            "A choice applies to servers started after it.",
        ]
    )


def doctor_text(report: Mapping[str, object]) -> str:
    """The install read top to bottom — interpreter, package, solver, the two directories, the
    databases, the page's address and each chatbot — with the step that supplies what a section
    lacks."""
    python = _map(report["python"])
    solver = _map(report["solver"])
    directories = _map(report["directories"])
    page = _map(report["view"])
    clients = _map(report["clients"])
    return "\n".join(
        [
            "EcoSemantic",
            _row("python", f"{python['executable']} ({python['version']})"),
            _row("package", report["ecosemantic"]),
            "Solver",
            _row("pardiso", "installed" if solver["pardiso"] else f"missing: {PARDISO}"),
            "Directories",
            _directory_row("data", _map(directories["data"])),
            _directory_row("systems", _map(directories["systems"])),
            "Databases",
            *_database_rows(report["databases"]),
            "Page",
            *_page_rows(page),
            "Telemetry",
            *_telemetry_rows(_map(report["telemetry"])),
            "Chatbots",
            *[_client_row(client, _map(answered)) for client, answered in clients.items()],
        ]
    )


def init_text(answer: Mapping[str, object]) -> str:
    """Where each chatbot connected gained this server, the install as it now stands, and the step
    that follows restarting the chatbot."""
    connected = cast("list[Mapping[str, object]]", answer["connected"])
    return "\n".join(
        [
            *(connect_text(item) for item in connected),
            doctor_text(_map(answer["doctor"])),
            str(answer["next"]),
        ]
    )


def refusal_text(envelope: ErrorEnvelope) -> str:
    """A refusal as a person reads it: the message, and the hint that says what to do about it."""
    if "hint" in envelope.details:
        return f"error: {envelope.message}\n{envelope.details['hint']}"
    return f"error: {envelope.message}"

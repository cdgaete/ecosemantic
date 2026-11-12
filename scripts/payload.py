"""The payload EcoSemantic Engine's Windows installer carries: python-build-standalone's CPython
with the core and its dependencies installed into it from the resolution `uv.lock` holds, its
third-party notices, and the numbers the installer holds the two data folders to.

    python scripts/payload.py lock --platform win-x64 --dist dist
    python scripts/payload.py build --platform win-x64 --dist dist --out OUT
    python scripts/payload.py requirements --payload OUT
    python scripts/payload.py notices --payload OUT --out OUT/THIRD_PARTY_NOTICES.txt
    python scripts/payload.py defines --payload OUT --out installer/windows/defines.iss
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPOSITORY))

INSTALLER = REPOSITORY / "installer"
PYTHON_RECORD = INSTALLER / "python.json"
BUDGETS = INSTALLER / "budgets.json"
CACHE = REPOSITORY / ".cache" / "payload"
RELEASE_BASE = "https://github.com/astral-sh/python-build-standalone/releases/download"
TIMEOUT_SECONDS = 1800


def _workspace_distributions() -> tuple[str, ...]:
    """The core's distributions, as the workspace's members name them."""
    from scripts.members import distributions

    return distributions()


CORE_DISTRIBUTIONS = _workspace_distributions()
CORE_EXTRAS = (("ecosemantic", "mkl"), ("ecosemantic", "tray"))
PLATFORMS = {"win-x64": "x86_64-pc-windows-msvc"}
PRUNED = (
    ("tcl",),
    ("Lib", "tkinter"),
    ("Lib", "idlelib"),
    ("Lib", "turtledemo"),
    ("DLLs", "_tkinter.pyd"),
    ("DLLs", "tcl86t.dll"),
    ("DLLs", "tk86t.dll"),
    ("Scripts",),
)
BUNDLED = {
    "OpenSSL": ("OpenSSL",),
    "libffi": ("libffi",),
    "SQLite": ("SQLite",),
    "zlib": ("zlib",),
    "expat": ("expat",),
    "mpdecimal": ("libmpdec",),
    "liblzma": ("liblzma", "XZ Utils"),
    "bzip2": ("bzip2",),
    "Microsoft Visual C++ runtime": ("Microsoft Distributable Code",),
}
LICENCE_FILE = re.compile(r"^(?:licen[cs]e|copying)", re.IGNORECASE)
LICENCE_DIRECTORIES = ("licenses", "licences", "copying")
PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^ ;\\]+)", re.MULTILINE)
LOCKED_AT = re.compile(r"^# ecosemantic==(?P<version>\S+)$", re.MULTILINE)
PIPELINE = "pip"


def canonical(name: str) -> str:
    """The spelling pip compares two project names by, as PEP 503 normalises them."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(text: str) -> list[str]:
    """The distributions a requirements file pins, each as the name pip compares."""
    return [canonical(match["name"]) for match in PIN.finditer(text)]


def locked_at(version: str) -> str:
    """The line a requirements file opens with, naming the core version it was exported at."""
    return f"# ecosemantic=={version}"


def locked_version(text: str) -> str:
    """The core version a requirements file was exported at."""
    found = LOCKED_AT.search(text)
    if found is None:
        raise SystemExit(f"the requirements file records no {locked_at('VERSION')} line")
    return found["version"]


def pruned(root: Path) -> list[Path]:
    """The entries of a payload that are removed before it is packed: Tcl/Tk, tkinter, idle and
    the turtle demo, the extension and the two DLLs they load, and the launchers pip writes."""
    return [root.joinpath(*parts) for parts in PRUNED if root.joinpath(*parts).exists()]


def longest_path(root: Path) -> tuple[str, int]:
    """The longest path beneath root and its length, measured from root and written with forward
    slashes. An empty directory counts: the installer creates it too."""
    longest = ("", 0)
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if len(relative) > longest[1]:
            longest = (relative, len(relative))
    return longest


@dataclass(frozen=True)
class Distribution:
    """One distribution a payload installs: the name and version its metadata states, the licence
    it declares, and the text of every licence file it ships."""

    name: str
    version: str
    declared: str
    files: tuple[tuple[str, str], ...]


def _header(metadata: str) -> dict[str, list[str]]:
    """The fields of a distribution's metadata, each with every value it carries, parsed as the
    email headers they are so a continued value keeps every line."""
    message = Parser().parsestr(metadata)
    fields: dict[str, list[str]] = {}
    for key, value in message.items():
        fields.setdefault(key, []).append(str(value))
    return fields


def _declared(fields: dict[str, list[str]]) -> str:
    """The licence a distribution's metadata declares: its expression, the licence field older
    metadata carries, or the licence classifiers, and empty when it states none."""
    expression = [value for value in fields.get("License-Expression", []) if value]
    if expression:
        return " ".join(expression[0].split())
    legacy = [value for value in fields.get("License", []) if value and value != "UNKNOWN"]
    if legacy:
        return " ".join(legacy[0].split())
    classifiers = [
        value for value in fields.get("Classifier", []) if value.startswith("License ::")
    ]
    return "; ".join(classifiers)


def _shipped(dist_info: Path) -> tuple[tuple[str, str], ...]:
    """The licence texts a distribution's metadata directory carries, at its root and beneath its
    licences directory, each by its path inside that directory."""
    found: list[tuple[str, str]] = []
    for path in sorted(dist_info.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(dist_info).parts
        named = len(parts) == 1 and LICENCE_FILE.match(parts[0]) is not None
        inside = len(parts) > 1 and parts[0].lower() in LICENCE_DIRECTORIES
        if named or inside:
            found.append(("/".join(parts), path.read_text(encoding="utf-8", errors="replace")))
    return tuple(found)


def distributions(site_packages: Path) -> list[Distribution]:
    """Every distribution a payload installs, by the name and version its metadata states."""
    found: list[Distribution] = []
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        fields = _header((dist_info / "METADATA").read_text(encoding="utf-8", errors="replace"))
        held = {key: values[0] for key, values in fields.items() if values}
        found.append(
            Distribution(
                name=held["Name"],
                version=held["Version"],
                declared=_declared(fields),
                files=_shipped(dist_info),
            )
        )
    return sorted(found, key=lambda one: (canonical(one.name), one.version))


def unnamed(text: str) -> list[str]:
    """The libraries the Windows payload links whose terms a licence text does not carry, each by
    the name the payload links it under; a library answers to every name its own statement uses."""
    held = text.lower()
    return [
        library
        for library, names in BUNDLED.items()
        if not any(name.lower() in held for name in names)
    ]


def notices(site_packages: Path, cpython_licence: str) -> str:
    """The third-party notice of a payload: CPython's own licence with the terms of every library
    its Windows build links, then every distribution the payload installs, with the licence its
    metadata declares and the text of every licence file it ships. A distribution that states no
    licence and ships no licence file is refused, and so is a CPython text that states no terms for
    a linked library; every offender is named at once, since their terms would be missing."""
    installed = distributions(site_packages)
    bare = [one for one in installed if not one.declared and not one.files]
    if bare:
        raise SystemExit(
            "these distributions state no licence and ship no licence file: "
            + ", ".join(f"{one.name} {one.version}" for one in bare)
        )
    missing = unnamed(cpython_licence)
    if missing:
        raise SystemExit(
            "the CPython texts state no terms for "
            + ", ".join(missing)
            + "; pin each library's own statement in installer/python.json"
        )
    counted = [
        one for one in installed if canonical(one.name) not in {*CORE_DISTRIBUTIONS, PIPELINE}
    ]
    lines = [
        "# Third-party notices",
        "",
        f"EcoSemantic Engine carries CPython and {len(counted)} distributions of other",
        "people's work in its `python` payload, its own seven distributions and pip beside",
        "them. This notice states the licence each one declares, and the text of every",
        "licence file it ships.",
        "",
        "## CPython",
        "",
        "CPython's own licence, and the terms of every library its Windows build links: the",
        "payload's `python/LICENSE.txt`, CPython's `Doc/license.rst`, and the statements pinned",
        "for the libraries neither names.",
        "",
        "````text",
        cpython_licence.strip("\n"),
        "````",
        "",
    ]
    for one in installed:
        lines += [
            f"## {one.name}@{one.version}",
            "",
            f"Declared licence: {one.declared or 'none stated'}",
            "",
        ]
        if not one.files:
            lines += ["This distribution ships no licence file.", ""]
        for name, text in one.files:
            lines += [f"### {name}", "", "````text", text.strip("\n"), "````", ""]
    return "\n".join(lines) + "\n"


def _record() -> dict[str, Any]:
    """`installer/python.json`, whose shape that file owns: the release, its version, each
    platform's asset, the CPython licence document's address and hash, and under `licence.bundled`
    a statement pinned for each library the CPython texts do not cover."""
    return json.loads(PYTHON_RECORD.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as opened:
        for block in iter(lambda: opened.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, target: Path, expected: str) -> Path:
    """The file at a URL, kept under target and checked against the hash it is pinned by. A file
    that does not hash to it is removed, and both hashes are named."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        held = _sha256(target)
        if held == expected:
            return target
        target.unlink()
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as answer:
        target.write_bytes(answer.read())
    held = _sha256(target)
    if held != expected:
        target.unlink()
        raise SystemExit(f"{url} hashes to {held}, not the published {expected}")
    return target


def _published(asset: str, release: str) -> str:
    """The hash a release's `SHA256SUMS` publishes for one asset."""
    url = f"{RELEASE_BASE}/{release}/SHA256SUMS"
    with urllib.request.urlopen(url, timeout=120) as answer:
        lines = answer.read().decode("utf-8").splitlines()
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == asset:
            return fields[0]
    raise SystemExit(f"{asset} is not among the sums {url} publishes")


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Run one command of the build in the folder and the environment given, and answer what it
    printed; a non-zero exit, a command that runs past the timeout or one that cannot start stops
    the build, naming the command and the last of what it printed."""
    try:
        finished = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
            cwd=cwd,
            env=None if env is None else {**os.environ, **env},
        )
    except FileNotFoundError as missing:
        raise SystemExit(f"{command[0]} is not on PATH") from missing
    except subprocess.TimeoutExpired as expired:
        printed = b"".join(part or b"" for part in (expired.stdout, expired.stderr)).decode(
            "utf-8", "replace"
        )
        raise SystemExit(
            f"{' '.join(command)} ran past {TIMEOUT_SECONDS} s\n{printed.strip()[-4000:]}"
        ) from expired
    out = finished.stdout.decode("utf-8", "replace")
    if finished.returncode != 0:
        err = finished.stderr.decode("utf-8", "replace")
        raise SystemExit(
            f"{' '.join(command)} ended {finished.returncode}\n"
            f"{out.strip()[-4000:]}\n{err.strip()[-4000:]}"
        )
    return out


def wheel_identity(path: Path) -> tuple[str, str]:
    """The distribution a wheel file carries and its version, the name as pip compares it."""
    parts = path.name[: -len(".whl")].split("-")
    if len(parts) < 5:
        raise SystemExit(f"{path.name} is not a wheel: it carries no name, version and tags")
    return canonical(parts[0]), parts[1]


def built_version(dist: Path) -> str:
    """The version the core's seven wheels in a build carry, refused when the build holds no wheel
    for one of them, when one distribution is there at two versions, and when the seven are not all
    one version; every distribution that differs is named with its versions."""
    found: dict[str, set[str]] = {}
    for path in sorted(dist.glob("*.whl")):
        name, version = wheel_identity(path)
        if name in CORE_DISTRIBUTIONS:
            found.setdefault(name, set()).add(version)
    missing = sorted(name for name in CORE_DISTRIBUTIONS if name not in found)
    if missing:
        raise SystemExit(f"{dist} holds no wheel for {', '.join(missing)}")
    twice = {name: sorted(versions) for name, versions in found.items() if len(versions) > 1}
    if twice:
        raise SystemExit(
            f"{dist} holds these distributions at more than one version: "
            + ", ".join(f"{name} {', '.join(versions)}" for name, versions in twice.items())
        )
    versions = sorted({version for held in found.values() for version in held})
    if len(versions) != 1:
        raise SystemExit(f"{dist} holds core wheels of {', '.join(versions)}")
    return versions[0]


def export_requirements(out: Path) -> None:
    """Export the resolution `uv.lock` holds for the payload's two extras: the set the suite tests,
    with a hash for every wheel, read from this repository's lock whatever folder asked."""
    _run(
        [
            "uv",
            "export",
            "--frozen",
            "--format",
            "requirements-txt",
            "--package",
            "ecosemantic",
            *[part for _, extra in CORE_EXTRAS for part in ("--extra", extra)],
            "--no-dev",
            "--no-emit-workspace",
            "--no-header",
            "-o",
            str(out),
        ],
        cwd=REPOSITORY,
    )


def workspace_version() -> str:
    """The core's version, as the installed distribution states it: the one `scripts/bump.sh` sets
    for the workspace."""
    return importlib.metadata.version("ecosemantic")


def lock(platform_name: str, dist: Path) -> Path:
    """Export the platform's requirements from `uv.lock`, record the core version they were
    exported at, and refresh the interpreter asset's published hash. The build in `dist` must be
    of the version the workspace carries."""
    if platform_name not in PLATFORMS:
        raise SystemExit(f"{platform_name} is not a payload platform; {', '.join(PLATFORMS)} is")
    version = workspace_version()
    built = built_version(dist)
    if built != version:
        raise SystemExit(
            f"the workspace is at ecosemantic {version}, and {dist} builds {built}; build it again"
        )
    record = _record()
    target = INSTALLER / f"{platform_name}.requirements.txt"
    exported = target.with_name(f".{target.name}")
    export_requirements(exported)
    body = exported.read_text(encoding="utf-8")
    exported.unlink()
    target.write_text(f"{locked_at(version)}\n{body}", encoding="utf-8", newline="\n")
    asset = record["assets"][platform_name]
    published = _published(asset["asset"], record["release"])
    if published != asset["sha256"]:
        asset["sha256"] = published
        PYTHON_RECORD.write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"{PYTHON_RECORD.name}: {asset['asset']} hashes to {published}")
    pinned = len(requirement_names(body))
    print(f"{target}: {pinned} requirements at ecosemantic {version} for {platform_name}")
    return target


def host_platform() -> str:
    """The payload platform this host builds, which is Windows on x86-64 alone."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win-x64"
    return f"{sys.platform}-{machine}"


def _remove(payload: Path) -> None:
    for path in pruned(payload):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _compiled(interpreter: Path, payload: Path, version: str) -> int:
    """Compile the payload's library to bytecode that stays valid whatever a copy does to a
    source's time, the payload's own path stripped from what each file records; the count of
    bytecode files written. A source the strip did not match is printed and stops the build."""
    library = payload / "Lib"
    printed = _run(
        [
            str(interpreter),
            "-X",
            "utf8",
            "-I",
            "-m",
            "compileall",
            "-f",
            "-q",
            "-j",
            "0",
            "-s",
            str(payload),
            "--invalidation-mode",
            "unchecked-hash",
            str(library),
        ]
    )
    unstripped = [line for line in printed.splitlines() if "is not a valid prefix" in line]
    if unstripped:
        raise SystemExit(
            f"{len(unstripped)} sources were compiled under {payload} without the strip:\n"
            + "\n".join(unstripped[:20])
        )
    tag = "".join(version.split(".")[:2])
    probe = library / "json" / "__pycache__" / f"__init__.cpython-{tag}.pyc"
    if not probe.is_file():
        raise SystemExit(f"compiling {library} left no {probe}")
    if str(payload).encode() in probe.read_bytes():
        raise SystemExit(f"{probe} records {payload}, so the strip compileall was given matched")
    return sum(1 for path in library.rglob("*.pyc"))


def _pip(interpreter: Path) -> tuple[list[str], dict[str, str]]:
    """The payload's own pip, in UTF-8 and isolated from a user site and the `PIP_*` variables, and
    the environment that keeps it from reading the global and site `pip.ini` too: `--isolated`
    leaves those two in place, and `PIP_CONFIG_FILE` naming the null device is what removes them."""
    command = [str(interpreter), "-X", "utf8", "-I", "-m", "pip", "--isolated"]
    return command, {"PIP_CONFIG_FILE": os.devnull}


@dataclass(frozen=True)
class PayloadRecord:
    """What a payload holds: the core and CPython versions it carries, how many files, and the
    longest path the installer's `{app}` receives."""

    core: str
    python: str
    files: int
    longest_path: str
    longest_length: int

    def document(self) -> dict[str, object]:
        """The record as `<out>/payload.json` holds it."""
        return {
            "core": self.core,
            "python": self.python,
            "files": self.files,
            "longest": {"path": self.longest_path, "length": self.longest_length},
        }

    def summary(self, out: Path, compiled: int) -> str:
        """The line a build prints last: what the payload carries and what it costs Windows."""
        return (
            f"{out}: CPython {self.python} with {self.core}, {self.files} files, "
            f"{compiled} modules compiled, the longest path {self.longest_length} characters"
        )


def record_payload(out: Path, *, core: str, python: str) -> PayloadRecord:
    """The payload's record, written to `<out>/payload.json`: the versions it carries, how many
    files it holds, and its longest path measured from the folder the installer's `{app}`
    receives, so it begins with `python/`."""
    files = sum(1 for path in (out / "python").rglob("*") if path.is_file())
    relative, length = longest_path(out)
    held = PayloadRecord(
        core=core, python=python, files=files, longest_path=relative, longest_length=length
    )
    (out / "payload.json").write_text(
        json.dumps(held.document(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return held


def emptied(out: Path) -> None:
    """Remove the folder a build writes into, refusing one that holds no `payload.json`: the folder
    a build is given is deleted whole, and a folder no earlier build wrote is not the build's to
    remove."""
    if not out.exists():
        return
    if not (out / "payload.json").is_file():
        raise SystemExit(
            f"{out} holds no payload.json, and a build deletes the folder it is given: give an "
            "empty path or the folder an earlier build wrote"
        )
    shutil.rmtree(out)


def build(platform_name: str, dist: Path, out: Path) -> dict[str, object]:
    """Unpack the interpreter one platform's record pins into `<out>/python`, install the locked
    wheels and then the core's seven from the build without their dependencies, remove what the
    payload never runs, check every requirement its metadata makes, compile its library, and write
    `<out>/payload.json`. The workspace's `ecosemantic` must be installed in the interpreter running
    this, which `uv run` gives, since the build is refused when it is not the version of the
    workspace."""
    host = host_platform()
    if platform_name != host:
        raise SystemExit(f"a {platform_name} payload is built on {platform_name}, not on {host}")
    resolved_out = out.resolve()
    resolved_dist = dist.resolve()
    if resolved_out == resolved_dist or resolved_dist.is_relative_to(resolved_out):
        raise SystemExit(f"{out} holds {dist}; build the payload into a folder beside it")
    version = built_version(dist)
    workspace = workspace_version()
    if version != workspace:
        raise SystemExit(
            f"the workspace is at ecosemantic {workspace}, and {dist} builds {version}; "
            "build it again"
        )
    requirements = INSTALLER / f"{platform_name}.requirements.txt"
    locked = locked_version(requirements.read_text(encoding="utf-8"))
    if locked != version:
        raise SystemExit(
            f"{requirements} was exported at ecosemantic {locked}, and {dist} builds {version}"
        )
    record = _record()
    asset = record["assets"][platform_name]
    archive = _download(
        f"{RELEASE_BASE}/{record['release']}/{asset['asset']}",
        CACHE / asset["asset"],
        asset["sha256"],
    )
    emptied(out)
    out.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(out, filter="data")
    payload = out / "python"
    interpreter = payload / "python.exe"
    if not interpreter.is_file():
        raise SystemExit(
            f"{archive} unpacked no python/python.exe into {out}, which holds "
            f"{sorted(path.name for path in out.iterdir())}"
        )
    _remove(payload)
    wheels = CACHE / f"wheels-{platform_name}"
    if wheels.exists():
        shutil.rmtree(wheels)
    pip, pip_environment = _pip(interpreter)
    _run(
        [
            *pip,
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--require-hashes",
            "--dest",
            str(wheels),
            "-r",
            str(requirements),
        ],
        env=pip_environment,
    )
    _run(
        [
            *pip,
            "install",
            "--no-index",
            "--find-links",
            str(wheels),
            "--require-hashes",
            "-r",
            str(requirements),
        ],
        env=pip_environment,
    )
    core = sorted(
        path for path in dist.glob("*.whl") if wheel_identity(path)[0] in CORE_DISTRIBUTIONS
    )
    _run(
        [*pip, "install", "--no-index", "--no-deps", *[str(path) for path in core]],
        env=pip_environment,
    )
    _remove(payload)
    _run(
        [
            str(interpreter),
            "-X",
            "utf8",
            "-I",
            str(Path(__file__).resolve()),
            "requirements",
            "--payload",
            str(out),
        ]
    )
    compiled = _compiled(interpreter, payload, record["version"])
    held = record_payload(out, core=version, python=record["version"])
    print(held.summary(out, compiled))
    return held.document()


def _packaging() -> tuple[Any, Any, Any]:
    """`packaging`'s requirement parser, name canonicaliser and marker environment, or the copy
    pip vendors when the interpreter running this carries none."""
    try:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
    except ImportError:
        from pip._vendor.packaging.markers import default_environment
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.utils import canonicalize_name
    return Requirement, canonicalize_name, default_environment


def requirement_gaps(site_packages: Path, roots: tuple[tuple[str, str], ...]) -> list[str]:
    """What the installed distributions' metadata requires and site-packages does not hold, or holds
    at a version the requirement refuses, each gap named with the requirement that asks for it and
    judged under the markers of the interpreter running this."""
    requirement_of, canonical_name, environment_of = _packaging()
    held: dict[str, list[str]] = {}
    versions: dict[str, str] = {}
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        fields = _header((dist_info / "METADATA").read_text(encoding="utf-8", errors="replace"))
        missing = [field for field in ("Name", "Version") if not fields.get(field, [""])[0]]
        if missing:
            raise SystemExit(f"{dist_info} states no {' and no '.join(missing)}")
        name = fields["Name"][0]
        held[canonical_name(name)] = fields.get("Requires-Dist", [])
        versions[canonical_name(name)] = fields["Version"][0]
    environment = environment_of()
    queue = [(canonical_name(name), extra) for name, extra in roots]
    seen: set[tuple[str, str]] = set()
    gaps: list[str] = []
    while queue:
        package, extra = queue.pop()
        if (package, extra) in seen or package not in held:
            continue
        seen.add((package, extra))
        for text in held[package]:
            requirement = requirement_of(text)
            if requirement.marker is not None and not requirement.marker.evaluate(
                dict(environment, extra=extra)
            ):
                continue
            target = canonical_name(requirement.name)
            queue.append((target, ""))
            queue.extend((target, wanted) for wanted in sorted(requirement.extras))
            asked_by = f"{package}[{extra}]" if extra else package
            if target not in held:
                gaps.append(f"{asked_by} requires {requirement}, and the payload holds no {target}")
            elif not requirement.specifier.contains(versions[target]):
                gaps.append(
                    f"{asked_by} requires {requirement}, and the payload holds {target} "
                    f"{versions[target]}"
                )
    return sorted(set(gaps))


def requirements(payload: Path) -> list[str]:
    """The requirements the payload's core distributions ask for and it does not hold."""
    site_packages = payload / "python" / "Lib" / "site-packages"
    roots = tuple((name, "") for name in CORE_DISTRIBUTIONS) + CORE_EXTRAS
    return requirement_gaps(site_packages, roots)


def write_notices(payload: Path, out: Path) -> str:
    """Write a payload's third-party notice: CPython's own `python/LICENSE.txt`, the pinned
    `Doc/license.rst` for the libraries it does not name, the pinned statement of each library
    neither CPython text names, and every distribution the payload installs."""
    record = _record()
    cpython_file = payload / "python" / "LICENSE.txt"
    if not cpython_file.is_file():
        raise SystemExit(f"{payload} carries no python/LICENSE.txt, so it has no CPython licence")
    texts = [cpython_file.read_text(encoding="utf-8", errors="replace")]
    missing = unnamed(texts[0])
    if missing:
        document = _download(
            record["licence"]["url"],
            CACHE / "license.rst",
            record["licence"]["sha256"],
        )
        texts.append(document.read_text(encoding="utf-8"))
        print(f"CPython's own file names no {', '.join(missing)}; license.rst is added")
    for library, pinned in record["licence"]["bundled"].items():
        statement = _download(pinned["url"], CACHE / Path(pinned["url"]).name, pinned["sha256"])
        texts.append(statement.read_text(encoding="utf-8"))
        print(f"{library} {pinned['version']}: {len(texts[-1].splitlines())} lines of terms")
    text = notices(
        payload / "python" / "Lib" / "site-packages",
        "\n\n".join(part.rstrip() for part in texts),
    )
    out.write_text(text, encoding="utf-8", newline="\n")
    installed = len(list((payload / "python" / "Lib" / "site-packages").glob("*.dist-info")))
    print(f"{out}: CPython and {installed} installed distributions noticed")
    return text


def defines(payload: Path, out: Path) -> list[str]:
    """Write the ISPP defines the installer reads: the payload's core version, its longest path,
    the two folders' budgets and its directory, absolute and in its long name."""
    held = json.loads((payload / "payload.json").read_text(encoding="utf-8"))
    budgets = json.loads(BUDGETS.read_text(encoding="utf-8"))
    lines = [
        f'#define AppVersion "{held["core"]}"',
        f"#define LongestPath {held['longest']['length']}",
        f"#define DatabasesBudget {budgets['databases']}",
        f"#define ModelsBudget {budgets['models']}",
        f'#define PayloadDir "{os.path.realpath(payload)}"',
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{out}: {len(lines)} defines")
    return lines


def main(argv: list[str]) -> int:
    """Run one subcommand of the payload build."""
    parser = argparse.ArgumentParser(
        prog="payload.py",
        description="Build the payload EcoSemantic Engine's Windows installer carries.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    locking = commands.add_parser("lock", help="export uv.lock's resolution for a platform")
    locking.add_argument("--platform", default="win-x64")
    locking.add_argument("--dist", type=Path, default=Path("dist"))
    building = commands.add_parser("build", help="unpack, install and compile a payload")
    building.add_argument("--platform", default="win-x64")
    building.add_argument("--dist", type=Path, default=Path("dist"))
    building.add_argument("--out", type=Path, required=True)
    checking = commands.add_parser(
        "requirements", help="name every requirement the payload does not hold"
    )
    checking.add_argument("--payload", type=Path, required=True)
    noticing = commands.add_parser("notices", help="write the payload's third-party notices")
    noticing.add_argument("--payload", type=Path, required=True)
    noticing.add_argument("--out", type=Path, required=True)
    defining = commands.add_parser("defines", help="write the installer's ISPP defines")
    defining.add_argument("--payload", type=Path, required=True)
    defining.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "lock":
        lock(arguments.platform, arguments.dist)
    elif arguments.command == "build":
        build(arguments.platform, arguments.dist, arguments.out)
    elif arguments.command == "requirements":
        gaps = requirements(arguments.payload)
        for gap in gaps:
            print(gap)
        return 1 if gaps else 0
    elif arguments.command == "notices":
        write_notices(arguments.payload, arguments.out)
    else:
        defines(arguments.payload, arguments.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

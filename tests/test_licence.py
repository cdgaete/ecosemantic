"""Every distribution carries the PolyForm Noncommercial 1.0.0 licence and Carlos Gaete-Morales's
required notice, and states both in its metadata."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
POLYFORM_NONCOMMERCIAL_SHA256 = "c0ea4a896d2c8c394b29f9427589996db826cd501c512279ff0ed3ef48fabbe5"
MEMBERS = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["tool"]["uv"]["workspace"][
    "members"
]


def project(member: str) -> dict:
    return tomllib.loads((REPOSITORY / member / "pyproject.toml").read_text())["project"]


def test_the_repository_carries_the_polyform_noncommercial_licence_and_the_notice() -> None:
    licence = (REPOSITORY / "LICENSE").read_bytes()
    # PolyForm-Noncommercial-1.0.0.md at tag 1.0.0 of github.com/polyformproject/polyform-licenses
    assert hashlib.sha256(licence).hexdigest() == POLYFORM_NONCOMMERCIAL_SHA256
    notice = (REPOSITORY / "NOTICE").read_text()
    assert (
        "Required Notice: Copyright 2026 Carlos Gaete-Morales "
        "(https://github.com/cdgaete/ecosemantic)" in notice.splitlines()
    )


@pytest.mark.parametrize("member", MEMBERS)
def test_each_distribution_carries_the_repository_s_licence_and_notice(member: str) -> None:
    for name in ("LICENSE", "NOTICE"):
        assert (REPOSITORY / member / name).read_bytes() == (REPOSITORY / name).read_bytes()


@pytest.mark.parametrize("member", MEMBERS)
def test_each_distribution_states_its_licence_readme_author_and_home(member: str) -> None:
    found = project(member)
    assert found["license"] == "PolyForm-Noncommercial-1.0.0"
    assert found["license-files"] == ["LICENSE", "NOTICE"]
    assert found["readme"] == "README.md" and (REPOSITORY / member / "README.md").is_file()
    assert found["authors"] == [{"name": "Carlos Gaete-Morales", "email": "cdgaete@gmail.com"}]
    assert set(found["urls"]) == {"Homepage", "Repository", "Issues", "Changelog"}
    assert all(
        url.startswith("https://github.com/cdgaete/ecosemantic") for url in found["urls"].values()
    )
    assert "Programming Language :: Python :: 3.12" in found["classifiers"]
    assert not [c for c in found["classifiers"] if c.startswith("License ::")]
    assert found["keywords"]


def test_the_page_states_the_licence() -> None:
    package = json.loads((REPOSITORY / "page" / "package.json").read_text())
    assert package["license"] == "PolyForm-Noncommercial-1.0.0"


def test_no_document_calls_the_package_open_source() -> None:
    # the Developer Certificate of Origin in CONTRIBUTING.md names an open source license; that
    # is the license a contribution comes under, not the repository's
    for name in ("README.md", "TELEMETRY.md", "CONTRIBUTING.md", "SECURITY.md", "TRADEMARK.md"):
        text = " ".join((REPOSITORY / name).read_text().lower().split())
        for claim in ("open core", "is open source", "open-source package", "free software"):
            assert claim not in text, (name, claim)
        assert "apache license" not in text or name == "CONTRIBUTING.md"


@pytest.mark.parametrize(
    "name", ["CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "TRADEMARK.md", "CHANGELOG.md"]
)
def test_the_repository_carries_its_community_files(name: str) -> None:
    text = (REPOSITORY / name).read_text()
    # a contact address the filler wrote, never a template's placeholder
    assert "@" in text or name in {"CONTRIBUTING.md", "CHANGELOG.md"}
    assert "[INSERT" not in text and "{CONTACT}" not in text

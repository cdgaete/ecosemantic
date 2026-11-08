"""The bridge's commands: what this engine's credential is, where it is kept, and what a start
that finds none says."""

from __future__ import annotations

import asyncio
import json
import webbrowser
from pathlib import Path
from uuid import uuid4

import httpx2
import keyring
import pytest
from keyring.backends.fail import Keyring as FailKeyring

from ecosemantic.bridge.credentials import NO_STORE, NO_STORE_HINT, Credential, store_for
from ecosemantic.bridge.signin import CREDENTIAL_KEPT
from ecosemantic.bridge.start import engine_version
from ecosemantic.cli import _parser, main
from tests.bridge.fake_logto import (
    ACCOUNT,
    BRIDGE,
    BROWSER_CLIENT_ID,
    HANDLE,
    PAGE_URL,
    REVOKE_PATH,
    USER_CODE,
    VERIFICATION_URI,
    FakeLogto,
)
from tests.bridge.test_credentials import LockedKeyring
from tests.bridge.test_signin import Browser
from tests.conftest import subcommands

NOT_SIGNED_IN = "this engine is not signed in to the bridge"
SIGN_IN = "ecosemantic bridge sign-in"
SIGN_OUT = "ecosemantic bridge sign-out"
NOTHING_REVOKED = "this systems directory is not signed in to the bridge; nothing was revoked"
RENEWAL = "a server serving this systems directory stops its bridge at its next token renewal"
ACCOUNT_PAGE = "on the bridge's account page"


def test_every_bridge_verb_binds_the_handler_and_the_renderer_that_answer_it() -> None:
    verbs = subcommands(subcommands(_parser())["bridge"])
    assert verbs
    for verb, parser in verbs.items():
        assert callable(parser.get_default("handler")), f"{verb} binds no handler"
        assert callable(parser.get_default("renderer")), f"{verb} binds no renderer"


def a_credential() -> Credential:
    """The credential a sign-in of this systems directory leaves behind."""
    return Credential(
        bridge_url=BRIDGE,
        client_id=BROWSER_CLIENT_ID,
        engine=uuid4(),
        account=ACCOUNT,
        handle=HANDLE,
        page_url=PAGE_URL,
        refresh_token="rt-1",
    )


def test_bridge_status_names_the_page_address_and_where_the_credential_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    store.save(credential)
    argv = ["bridge", "status", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    assert main([*argv, "--json"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer == {
        "signed_in": True,
        "handle": HANDLE,
        "page": PAGE_URL,
        "engine": str(credential.engine),
        "where": store.where,
    }
    assert main(argv) == 0
    text = capsys.readouterr().out
    assert HANDLE in text
    assert PAGE_URL in text
    assert store.where in text


def test_bridge_status_without_a_credential_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    credential_file = tmp_path / "credential.json"
    argv = [
        "bridge",
        "status",
        "--bridge-url",
        BRIDGE,
        "--credential-file",
        str(credential_file),
        "--systems-dir",
        str(tmp_path),
    ]
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": False,
        "where": f"the file {credential_file}",
    }
    assert main(argv) == 0
    text = capsys.readouterr().out
    assert "not signed in" in text and SIGN_IN in text


def test_bridge_status_names_the_variable_an_engine_token_comes_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = tmp_path / "token"
    token.write_text("the-engine-token", encoding="utf-8")
    token.chmod(0o600)
    argv = ["bridge", "status", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_TOKEN_FILE", str(token))
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": True,
        "where": "ECOSEMANTIC_BRIDGE_TOKEN_FILE",
    }
    monkeypatch.delenv("ECOSEMANTIC_BRIDGE_TOKEN_FILE")
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_TOKEN", "the-engine-token")
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": True,
        "where": "ECOSEMANTIC_BRIDGE_TOKEN",
    }


async def test_bridge_status_never_reaches_the_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reached: list[str] = []

    async def unreachable(request: httpx2.Request) -> httpx2.Response:
        reached.append(str(request.url))
        raise AssertionError(f"bridge status reaches {request.url}")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(unreachable)) as http:
        monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
        store_for(BRIDGE, tmp_path, None).save(a_credential())
        argv = ["bridge", "status", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
        assert main([*argv, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["signed_in"] is True
    assert reached == []


def test_bridge_sign_in_on_a_machine_without_a_store_names_both_other_ways(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    argv = ["bridge", "sign-in", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    assert main(argv) == 1
    error = capsys.readouterr().err
    assert "no credential store" in error
    assert "--credential-file" in error
    assert "ECOSEMANTIC_BRIDGE_TOKEN_FILE" in error


def test_serve_with_the_bridge_and_no_credential_off_a_terminal_exits_naming_sign_in(
    bundle_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logto = FakeLogto()
    opened: list[httpx2.AsyncClient] = []

    def a_client() -> httpx2.AsyncClient:
        opened.append(httpx2.AsyncClient(transport=logto.transport))
        return opened[-1]

    monkeypatch.setattr("ecosemantic.bridge.start.client", a_client)
    argv = [
        "serve",
        "--bridge",
        "--bridge-url",
        BRIDGE,
        "--data-dir",
        str(bundle_dir),
        "--systems-dir",
        str(tmp_path),
    ]
    assert main(argv) == 1
    error = capsys.readouterr().err
    assert NOT_SIGNED_IN in error
    assert SIGN_IN in error
    assert opened == []


def test_bridge_sign_in_with_the_device_flow_answers_the_connector_and_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    logto.interval = 0
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = [
        "bridge",
        "sign-in",
        "--device",
        "--name",
        "workstation",
        "--bridge-url",
        BRIDGE,
        "--systems-dir",
        str(tmp_path),
        "--json",
    ]
    try:
        assert main(argv) == 0
        captured = capsys.readouterr()
    finally:
        asyncio.run(http.aclose())
    assert json.loads(captured.out) == {
        "connector": f"{BRIDGE}/mcp",
        "page": PAGE_URL,
        "where": store_for(BRIDGE, tmp_path, None).where,
    }
    assert USER_CODE in captured.err and VERIFICATION_URI in captured.err
    assert logto.registrations == [
        {
            "engine": logto.registrations[0]["engine"],
            "name": "workstation",
            "version": engine_version(),
        }
    ]


def test_bridge_sign_out_revokes_the_grant_and_says_where_it_was_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store.save(credential)
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 0
        text = capsys.readouterr().out
    finally:
        asyncio.run(http.aclose())
    assert text.startswith(f"signed out of {BRIDGE}")
    assert str(credential.engine) in text
    assert store.where in text
    assert RENEWAL in text
    assert store.load() is None
    assert credential.refresh_token in logto.revoked


def test_bridge_sign_out_answers_the_bridge_the_engine_and_the_store_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store.save(credential)
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = [
        "bridge",
        "sign-out",
        "--bridge-url",
        BRIDGE,
        "--systems-dir",
        str(tmp_path),
        "--json",
    ]
    try:
        assert main(argv) == 0
        answer = json.loads(capsys.readouterr().out)
    finally:
        asyncio.run(http.aclose())
    assert answer == {
        "signed_out": True,
        "bridge": BRIDGE,
        "engine": str(credential.engine),
        "where": store.where,
    }
    assert credential.refresh_token in logto.revoked


def test_bridge_sign_out_refuses_an_engine_token_and_keeps_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    store.save(credential)
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_TOKEN", "the-engine-token")
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 1
        error = capsys.readouterr().err
    finally:
        asyncio.run(http.aclose())
    assert "ECOSEMANTIC_BRIDGE_TOKEN" in error
    assert ACCOUNT_PAGE in error
    assert store.load() == credential
    assert logto.requests == []


def test_bridge_sign_out_with_nothing_stored_answers_nothing_was_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    credential_file = tmp_path / "credential.json"
    opened: list[httpx2.AsyncClient] = []

    def a_client() -> httpx2.AsyncClient:
        opened.append(httpx2.AsyncClient(transport=logto.transport))
        return opened[-1]

    monkeypatch.setattr("ecosemantic.cli.client", a_client)
    argv = [
        "bridge",
        "sign-out",
        "--bridge-url",
        BRIDGE,
        "--credential-file",
        str(credential_file),
        "--systems-dir",
        str(tmp_path),
    ]
    try:
        assert main([*argv, "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == {
            "signed_out": False,
            "bridge": BRIDGE,
            "where": f"the file {credential_file}",
        }
        assert main(argv) == 0
        assert capsys.readouterr().out == f"{NOTHING_REVOKED}\n"
    finally:
        asyncio.run(opened[0].aclose())
        asyncio.run(opened[1].aclose())
    assert logto.requests == []


def test_bridge_sign_out_whose_revocation_fails_keeps_the_credential_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    logto.failures.add(REVOKE_PATH)
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store.save(credential)
    opened: list[httpx2.AsyncClient] = []

    def a_client() -> httpx2.AsyncClient:
        opened.append(httpx2.AsyncClient(transport=logto.transport))
        return opened[-1]

    monkeypatch.setattr("ecosemantic.cli.client", a_client)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 1
        error = capsys.readouterr().err
        assert "kept" in error
        assert SIGN_OUT in error
        assert ACCOUNT_PAGE in error
        assert store.load() == credential
        assert main([*argv, "--json"]) == 1
        refused = json.loads(capsys.readouterr().err)
    finally:
        for client_opened in opened:
            asyncio.run(client_opened.aclose())
    assert refused["details"]["hint"] == CREDENTIAL_KEPT
    assert store.load() == credential


def test_bridge_sign_out_refuses_an_engine_token_before_answering_nothing_was_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_TOKEN", "the-engine-token")
    logto = FakeLogto()
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 1
        error = capsys.readouterr().err
    finally:
        asyncio.run(http.aclose())
    assert "ECOSEMANTIC_BRIDGE_TOKEN names an engine token" in error
    assert ACCOUNT_PAGE in error
    assert NOTHING_REVOKED not in error
    assert logto.requests == []


def test_bridge_sign_out_refuses_a_blank_engine_token_with_its_own_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_for(BRIDGE, tmp_path, None)
    credential = a_credential()
    store.save(credential)
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_TOKEN", "")
    logto = FakeLogto()
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 1
        error = capsys.readouterr().err
    finally:
        asyncio.run(http.aclose())
    assert "ECOSEMANTIC_BRIDGE_TOKEN holds no engine token" in error
    assert ACCOUNT_PAGE not in error
    assert store.load() == credential
    assert logto.requests == []


def test_bridge_sign_out_on_a_credential_store_that_fails_at_use_keeps_its_own_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: LockedKeyring())
    logto = FakeLogto()
    opened: list[httpx2.AsyncClient] = []

    def a_client() -> httpx2.AsyncClient:
        opened.append(httpx2.AsyncClient(transport=logto.transport))
        return opened[-1]

    monkeypatch.setattr("ecosemantic.cli.client", a_client)
    argv = ["bridge", "sign-out", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main([*argv, "--json"]) == 1
        refused = json.loads(capsys.readouterr().err)
        assert refused["error"] == "unavailable"
        assert refused["message"] == NO_STORE
        assert refused["details"] == {"hint": NO_STORE_HINT}
        assert main(argv) == 1
        assert capsys.readouterr().err == f"error: {NO_STORE}\n{NO_STORE_HINT}\n"
    finally:
        for client_opened in opened:
            asyncio.run(client_opened.aclose())
    assert logto.requests == []


def test_bridge_status_on_a_credential_store_that_fails_at_use_exits_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: LockedKeyring())
    argv = ["bridge", "status", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    assert main([*argv, "--json"]) == 1
    refused = json.loads(capsys.readouterr().err)
    assert refused["error"] == "unavailable"
    assert refused["message"] == NO_STORE
    assert refused["details"] == {"hint": NO_STORE_HINT}
    assert main(argv) == 1
    assert capsys.readouterr().err == f"error: {NO_STORE}\n{NO_STORE_HINT}\n"


def test_bridge_status_on_a_machine_without_a_credential_store_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    argv = ["bridge", "status", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": False,
        "where": None,
        "hint": NO_STORE_HINT,
    }
    assert main(argv) == 0
    assert capsys.readouterr().out == (
        f"not signed in; this machine has no credential store: {NO_STORE_HINT}\n"
    )


def test_bridge_status_with_a_credential_file_answers_on_a_machine_without_a_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    credential_file = tmp_path / "credential.json"
    store = store_for(BRIDGE, tmp_path, credential_file)
    credential = a_credential()
    store.save(credential)
    argv = [
        "bridge",
        "status",
        "--bridge-url",
        BRIDGE,
        "--credential-file",
        str(credential_file),
        "--systems-dir",
        str(tmp_path),
        "--json",
    ]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": True,
        "handle": HANDLE,
        "page": PAGE_URL,
        "engine": str(credential.engine),
        "where": store.where,
    }


def test_bridge_sign_out_on_a_machine_without_a_credential_store_answers_nothing_was_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    logto = FakeLogto()
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = [
        "bridge",
        "sign-out",
        "--bridge-url",
        BRIDGE,
        "--systems-dir",
        str(tmp_path),
        "--json",
    ]
    try:
        assert main(argv) == 0
        assert json.loads(capsys.readouterr().out) == {
            "signed_out": False,
            "bridge": BRIDGE,
            "where": None,
        }
    finally:
        asyncio.run(http.aclose())
    assert logto.requests == []


def test_bridge_status_reads_the_variables_that_stand_in_for_the_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_URL", BRIDGE)
    store_for(BRIDGE, tmp_path, None).save(a_credential())
    argv = ["bridge", "status", "--systems-dir", str(tmp_path)]
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["page"] == PAGE_URL
    credential_file = tmp_path / "credential.json"
    monkeypatch.setenv("ECOSEMANTIC_BRIDGE_CREDENTIAL_FILE", str(credential_file))
    assert main([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signed_in": False,
        "where": f"the file {credential_file}",
    }


def test_bridge_sign_in_opens_the_browser_when_the_machine_shows_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    monkeypatch.setattr(webbrowser, "open", browser)
    monkeypatch.setattr("ecosemantic.serve.browser_reachable", lambda environ, platform: True)
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.cli.client", lambda: http)
    argv = ["bridge", "sign-in", "--bridge-url", BRIDGE, "--systems-dir", str(tmp_path)]
    try:
        assert main(argv) == 0
        text = capsys.readouterr().out
    finally:
        asyncio.run(http.aclose())
    browser.finished()
    assert len(browser.urls) == 1
    assert text.startswith(f"add {BRIDGE}/mcp as a connector in your chat")
    assert PAGE_URL in text

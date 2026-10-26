from __future__ import annotations

from pathlib import Path

from ecosemantic.cli.doctor import report
from ecosemantic.cli.text import (
    connect_text,
    database_text,
    doctor_text,
    init_text,
    refusal_text,
    terms_text,
)
from ecosemantic.errors import ErrorEnvelope


def test_doctor_names_the_step_that_supplies_each_lack(tmp_path: Path) -> None:
    data, systems = tmp_path / "data", tmp_path / "systems"
    text = doctor_text(report(data, systems, []))
    assert "EcoSemantic" in text and "Databases" in text
    assert "ecosemantic setup uslci" in text
    assert "ecosemantic connect claude-desktop" in text
    assert "the server makes it on its first start" in text


def test_doctor_names_the_databases_it_holds_and_the_clients_it_finds(tmp_path: Path) -> None:
    answered = report(tmp_path / "data", tmp_path / "systems", ["fixture"])
    clients = {
        "claude-desktop": {
            "path": "/home/person/Claude.json",
            "present": True,
            "command": "/usr/bin/gone",
            "command_exists": False,
        },
        "cursor": {
            "path": "/home/person/.cursor/mcp.json",
            "present": True,
            "command": "/usr/bin/ecosemantic",
            "command_exists": True,
        },
        "vscode": {"path": "/w/.vscode/mcp.json", "present": True, "error": "no JSON object"},
    }
    text = doctor_text({**answered, "clients": clients})
    assert "fixture" in text
    assert "configured" in text and "no JSON object" in text
    assert "its command is not installed" in text
    unreadable = {**answered, "databases": {"error": "unavailable", "message": "held"}}
    assert "unreadable" in doctor_text({**unreadable, "clients": clients})


def test_a_label_wider_than_its_column_stays_apart_from_its_value(tmp_path: Path) -> None:
    answered = report(tmp_path / "data", tmp_path / "systems", [])
    clients = {"claude-desktop": {"documented": False, "message": "m"}}
    text = doctor_text({**answered, "clients": clients})
    assert "  claude-desktop no documented location (m)" in text


def test_a_refusal_shows_its_message_and_its_hint() -> None:
    assert (
        refusal_text(ErrorEnvelope(error="unavailable", message="m", details={"hint": "h"}))
        == "error: m\nh"
    )


def test_a_refusal_without_a_hint_is_its_message_alone() -> None:
    assert refusal_text(ErrorEnvelope(error="invalid", message="m")) == "error: m"


def test_the_terms_name_the_licence_file_the_citation_and_the_flag() -> None:
    text = terms_text(Path("/downloads/licence.txt"), "a citation")
    assert "a citation" in text and str(Path("/downloads/licence.txt")) in text
    assert "Run the command again with --accept-terms to accept them." in text


def test_a_database_answer_names_what_it_wrote_or_what_it_loaded() -> None:
    written = database_text({"bundle": "work.zip", "mode": "working", "systems": 1, "datasets": 4})
    assert "work.zip" in written and "working" in written and "4" in written
    released = database_text({"database": "rel", "datasets": 4})
    assert released.startswith("loaded rel") and "4" in released
    restored = database_text({"base": "kept", "systems": {"1": "added"}})
    assert "kept" in restored and "added" in restored


def test_a_connect_answer_names_where_and_what_it_replaced() -> None:
    answer = {
        "client": "cursor",
        "path": "/home/person/.cursor/mcp.json",
        "server": "ecosemantic",
        "command": "/usr/bin/ecosemantic",
        "replaced": True,
    }
    text = connect_text(answer)
    assert "/home/person/.cursor/mcp.json" in text and "replaced" in text
    assert "added" in connect_text({**answer, "replaced": False})


def test_an_init_answer_names_each_chatbot_connected_the_report_and_the_next_step() -> None:
    answer = {
        "connected": [
            {
                "client": "cursor",
                "path": "/home/person/.cursor/mcp.json",
                "server": "ecosemantic",
                "command": "/usr/bin/ecosemantic",
                "replaced": False,
            }
        ],
        "doctor": report(Path("/data"), Path("/systems"), []),
        "next": "Restart your chatbot; the EcoSemantic page opens in your browser.",
    }
    text = init_text(answer)
    assert "/home/person/.cursor/mcp.json" in text
    assert "EcoSemantic" in text and "Restart your chatbot" in text

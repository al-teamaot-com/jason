from __future__ import annotations

import json
from pathlib import Path

from jason_cli import __main__
from jason_cli import autotask


def test_describe_command(monkeypatch, capsys) -> None:
    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {
            "entity": "Invoices",
            "supportsQuery": True,
        }

    monkeypatch.setattr(
        autotask,
        "execute_autotask",
        fake_execute,
    )

    result = __main__.main(
        ["autotask", "describe", "Invoices"]
    )

    assert result == 0
    assert calls[0]["capability"] == (
        "autotask.entity.describe"
    )
    assert calls[0]["arguments"] == {
        "entity": "Invoices"
    }

    output = json.loads(capsys.readouterr().out)
    assert output["entity"] == "Invoices"


def test_get_command(monkeypatch) -> None:
    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {"item": {"id": 134952}}

    monkeypatch.setattr(
        autotask,
        "execute_autotask",
        fake_execute,
    )

    result = __main__.main(
        [
            "autotask",
            "get",
            "Tickets",
            "134952",
        ]
    )

    assert result == 0
    assert calls[0]["capability"] == (
        "autotask.entity.get"
    )
    assert calls[0]["arguments"] == {
        "entity": "Tickets",
        "entity_id": 134952,
    }


def test_query_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    search_file = tmp_path / "query.json"
    search_file.write_text(
        json.dumps(
            {
                "MaxRecords": 10,
                "filter": [
                    {
                        "op": "eq",
                        "field": "status",
                        "value": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {"items": []}

    monkeypatch.setattr(
        autotask,
        "execute_autotask",
        fake_execute,
    )

    result = __main__.main(
        [
            "autotask",
            "query",
            "Tickets",
            "--search-file",
            str(search_file),
        ]
    )

    assert result == 0
    assert calls[0]["capability"] == (
        "autotask.entity.query"
    )
    assert calls[0]["arguments"]["entity"] == (
        "Tickets"
    )

    parsed_search = json.loads(
        calls[0]["arguments"]["search"]
    )
    assert parsed_search["MaxRecords"] == 10


def test_invalid_search_file_returns_error(
    tmp_path: Path,
    capsys,
) -> None:
    search_file = tmp_path / "bad.json"
    search_file.write_text(
        "not json",
        encoding="utf-8",
    )

    result = __main__.main(
        [
            "autotask",
            "query",
            "Tickets",
            "--search-file",
            str(search_file),
        ]
    )

    assert result == 1
    assert "invalid JSON" in capsys.readouterr().err

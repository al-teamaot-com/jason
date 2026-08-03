from __future__ import annotations

import json
from pathlib import Path

from jason_cli import __main__
from jason_cli import autotask


def test_describe_uses_human_readable_output(
    monkeypatch,
    capsys,
) -> None:
    def fake_execute(**kwargs):
        return {
            "info": {
                "name": "Ticket",
                "canQuery": True,
                "canCreate": True,
                "canUpdate": True,
                "canDelete": False,
                "userAccessForQuery": "All",
            }
        }

    monkeypatch.setattr(
        autotask,
        "execute_autotask",
        fake_execute,
    )

    result = __main__.main(
        ["autotask", "describe", "Tickets"]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Autotask entity: Tickets" in output
    assert "Supports Query: Yes" in output
    assert "Current Query Access: All" in output


def test_describe_json_output(
    monkeypatch,
    capsys,
) -> None:
    def fake_execute(**kwargs):
        return {
            "info": {
                "name": "Ticket",
                "canQuery": True,
            }
        }

    monkeypatch.setattr(
        autotask,
        "execute_autotask",
        fake_execute,
    )

    result = __main__.main(
        [
            "autotask",
            "describe",
            "Tickets",
            "--json",
        ]
    )

    assert result == 0

    output = json.loads(capsys.readouterr().out)
    assert output["info"]["name"] == "Ticket"


def test_get_uses_compact_output(
    monkeypatch,
    capsys,
) -> None:
    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {
            "item": {
                "id": 134952,
                "ticketNumber": "T20260630.0016",
                "title": "Synthetic ticket",
                "status": 1,
                "description": "Not printed by default.",
            }
        }

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

    output = capsys.readouterr().out

    assert result == 0
    assert calls[0]["capability"] == (
        "autotask.entity.get"
    )
    assert "Ticket Number: T20260630.0016" in output
    assert "Title: Synthetic ticket" in output
    assert "Not printed by default." not in output


def test_get_json_output(
    monkeypatch,
    capsys,
) -> None:
    def fake_execute(**kwargs):
        return {
            "item": {
                "id": 134952,
                "description": "Full response",
            }
        }

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
            "--json",
        ]
    )

    assert result == 0

    output = json.loads(capsys.readouterr().out)
    assert output["item"]["description"] == (
        "Full response"
    )


def test_query_uses_compact_output(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
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
        return {
            "items": [
                {
                    "id": 134952,
                    "ticketNumber": "T20260630.0016",
                    "title": "Synthetic ticket",
                    "description": "Not printed.",
                }
            ],
            "pageDetails": {
                "count": 1,
                "requestCount": 10,
            },
        }

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

    output = capsys.readouterr().out

    assert result == 0
    assert "Matches returned: 1" in output
    assert "Ticket Number: T20260630.0016" in output
    assert "Not printed." not in output


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

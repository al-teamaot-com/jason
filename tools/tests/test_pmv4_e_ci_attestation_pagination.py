"""Regression tests for PMv4 protected CI check-run pagination."""
import json
from types import SimpleNamespace

import pytest

from tools import pmv4_e_canary_oneowner_root as root


def _rows(start: int, count: int) -> list[dict]:
    return [{"name": f"check-{i}"} for i in range(start, start + count)]


def test_gh_api_collects_all_check_run_pages(monkeypatch):
    monkeypatch.setattr(root.os, "geteuid", lambda: 1000)
    pages = [
        {"count": 124, "rows": _rows(0, 100)},
        {"count": 124, "rows": _rows(100, 24)},
    ]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(pages[len(commands) - 1]), stderr=""
        )

    monkeypatch.setattr(root.subprocess, "run", runner)
    result = root.gh_api(
        "repos/al-teamaot-com/jason/commits/"
        "510243494efcd592a1585c681a3fa28a29296e17/check-runs?per_page=100",
        "{count:.total_count,rows:[.check_runs[]|{name}]}"
    )

    assert result["count"] == 124
    assert len(result["rows"]) == 124
    assert commands[0][-3].endswith("?per_page=100&page=1")
    assert commands[1][-3].endswith("?per_page=100&page=2")


def test_gh_api_rejects_check_count_change_during_pagination(monkeypatch):
    monkeypatch.setattr(root.os, "geteuid", lambda: 1000)
    pages = [
        {"count": 124, "rows": _rows(0, 100)},
        {"count": 125, "rows": _rows(100, 25)},
    ]
    calls = 0

    def runner(command, **kwargs):
        nonlocal calls
        response = pages[calls]
        calls += 1
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(response), stderr=""
        )

    monkeypatch.setattr(root.subprocess, "run", runner)
    with pytest.raises(root.Denied, match="GITHUB_CHECK_TOTAL_CHANGED_DURING_PAGINATION"):
        root.gh_api(
            "repos/al-teamaot-com/jason/commits/"
            "510243494efcd592a1585c681a3fa28a29296e17/check-runs?per_page=100",
            "{count:.total_count,rows:[.check_runs[]|{name}]}"
        )

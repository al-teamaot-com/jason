from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools import owner_identity_recovery as cli
from orchestrator.owner_identity_recovery import RecoveryDenied


def test_allowlist_verified_from_live_running_server(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd == ["docker", "inspect", "jason-mcp-pilot"]
        return SimpleNamespace(stdout=json.dumps([{
            "State": {"Running": True},
            "Config": {"Env": [
                "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-al",
                "SOME_OTHER_SECRET=NEVER_PRINT_OR_USE",
            ]},
        }]))
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.live_owner_allowlist() == frozenset({"person-al"})


def test_offline_mcp_cannot_supply_owner_allowlist(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=json.dumps([{"State": {"Running": False}, "Config": {"Env": []}}])
        ),
    )
    with pytest.raises(RecoveryDenied, match="RECOVERY_LIVE_MCP_CONTAINER_REQUIRED"):
        cli.live_owner_allowlist()


@pytest.mark.parametrize("uid,tty,operator,denial", [
    (1000, True, "al", "RECOVERY_LOCAL_ROOT_TTY_REQUIRED"),
    (0, False, "al", "RECOVERY_LOCAL_ROOT_TTY_REQUIRED"),
    (0, True, "", "RECOVERY_INDIVIDUAL_SUDO_OPERATOR_REQUIRED"),
])
def test_privilege_and_human_console_required(monkeypatch, uid, tty, operator, denial):
    monkeypatch.setattr(cli.os, "geteuid", lambda: uid)
    monkeypatch.setattr(cli.os, "isatty", lambda _: tty)
    monkeypatch.setenv("SUDO_USER", operator)
    with pytest.raises(RecoveryDenied, match=denial):
        cli.assert_human_local_approval("abcd" * 16, "person-al")


def test_wrong_human_challenge_cannot_recover(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli.os, "isatty", lambda _: True)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr("builtins.input", lambda _: "proceed")
    with pytest.raises(RecoveryDenied, match="RECOVERY_HUMAN_LOCAL_APPROVAL_MISMATCH"):
        cli.assert_human_local_approval("abcd" * 16, "person-al")


def test_exact_local_human_challenge(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli.os, "isatty", lambda _: True)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(
        "builtins.input", lambda _: "RECOVER person-al " + "abcd" * 4,
    )
    assert cli.assert_human_local_approval("abcd" * 16, "person-al") == "al"


def test_rollback_requires_distinct_human_challenge(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli.os, "isatty", lambda _: True)
    monkeypatch.setenv("SUDO_USER", "al")
    digest = "abcd" * 16
    monkeypatch.setattr("builtins.input", lambda _: "RECOVER person-al " + digest[:16])
    with pytest.raises(RecoveryDenied, match="RECOVERY_HUMAN_LOCAL_APPROVAL_MISMATCH"):
        cli.assert_human_local_approval(digest, "person-al", "ROLLBACK")
    monkeypatch.setattr("builtins.input", lambda _: "ROLLBACK person-al " + digest[:16])
    assert cli.assert_human_local_approval(digest, "person-al", "ROLLBACK") == "al"


def test_nonproduction_databases_cannot_be_mutated_using_local_recovery_cli(tmp_path):
    with pytest.raises(RecoveryDenied, match="RECOVERY_PRODUCTION_DATABASE_PATH_REQUIRED"):
        cli.assert_production_targets(
            tmp_path / "other-binding.sqlite3",
            cli.DEFAULT_AUTHORITY,
        )
    with pytest.raises(RecoveryDenied, match="RECOVERY_PRODUCTION_DATABASE_PATH_REQUIRED"):
        cli.assert_production_targets(
            cli.DEFAULT_BINDINGS,
            tmp_path / "other-authority.sqlite3",
        )

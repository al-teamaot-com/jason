"""Stage D independent read service is config-only and read-only."""
import json
import socket
import threading
import sqlite3
from pathlib import Path

import pytest

from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from autonomous_remediation.runbook_management_read_service import (
    _Server, _Handler, snapshot, RunbookReadServiceDenied,
)
from tools.pmv4_runbook_lifecycle_acceptance import sample


@pytest.fixture
def registry(tmp_path):
    db = tmp_path / "json-playbooks.sqlite3"
    store = SQLitePlaybookRegistry(db)
    store.close()
    return db


def lifecycle(db, operation):
    store = SQLitePlaybookRegistry(db)
    try:
        if operation == "activate":
            staged = store.stage(sample(), actor="synthetic-technician")
            store.activate(staged.document.playbook_id, staged.document.version,
                           actor="synthetic-owner",
                           expected_fingerprint=staged.document.fingerprint)
        elif operation == "retire":
            store.retire("pmv4_acceptance_repair", actor="synthetic-owner")
    finally:
        store.close()


def test_snapshot_is_read_only_and_hot_loads_existing_registry(registry):
    initial = registry.stat()
    assert snapshot(registry) == {
        "status": "healthy", "schema_version": 1, "registry_generation": 0,
        "active_count": 0, "active": [], "provider_calls": False,
        "execution_authority": False, "configuration_mutations": False,
    }
    lifecycle(registry, "activate")
    active = snapshot(registry, include_documents=True)
    assert active["registry_generation"] == 2
    assert active["active_count"] == 1
    assert active["active"][0]["playbook_id"] == "pmv4_acceptance_repair"
    assert active["active"][0]["definition"]["scope"]["direct_provider_access"] is False
    assert active["provider_calls"] is False
    assert active["execution_authority"] is False
    lifecycle(registry, "retire")
    assert snapshot(registry)["registry_generation"] == 3
    assert snapshot(registry)["active_count"] == 0
    assert registry.stat().st_ino == initial.st_ino


def test_audit_tampering_fails_closed(registry):
    lifecycle(registry, "activate")
    with sqlite3.connect(str(registry)) as con:
        con.execute("DELETE FROM json_playbook_lifecycle_events")
    with pytest.raises(RuntimeError, match="AUDIT_MISMATCH"):
        snapshot(registry)


def test_untrusted_registry_rejected(tmp_path, registry):
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(registry)
    with pytest.raises(RuntimeError, match="UNTRUSTED"):
        snapshot(alias)


def test_socket_reuses_existing_identity_and_forbids_writes(registry, tmp_path):
    parent = tmp_path / "socket"
    parent.mkdir(mode=0o700)
    sock = parent / "read.sock"
    server = _Server(sock, registry)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    def request(data):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(str(sock))
            s.sendall(data + b"\n")
            return json.loads(s.makefile("rb").readline())
    try:
        assert request(b'{"operation":"status"}')["registry_generation"] == 0
        assert request(b'{"operation":"stage"}')["status"] == "rejected"
        assert request(b'{"operation":"status","actor":"owner"}')["status"] == "rejected"
        lifecycle(registry, "activate")
        assert request(b'{"operation":"snapshot"}')["active_count"] == 1
        assert sock.stat().st_mode & 0o777 == 0o600
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert not sock.exists()


def test_socket_refuses_world_readable_parent(registry, tmp_path):
    parent = tmp_path / "unsafe"
    parent.mkdir(mode=0o755)
    with pytest.raises(RunbookReadServiceDenied, match="DIRECTORY_UNTRUSTED"):
        _Server(parent / "read.sock", registry)


def test_install_service_keeps_original_mcp_identity_and_no_provider_network():
    unit = (Path(__file__).resolve().parents[1]
            / "infrastructure/pmv4-runbook-management/jason-runbook-management-read.service").read_text()
    assert "User=al" in unit
    assert "RestrictAddressFamilies=AF_UNIX" in unit
    assert "IPAddressDeny=any" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "RuntimeDirectoryMode=0700" in unit
    assert "jason-runtime" not in unit
    assert "jason-mcp-pilot" not in unit

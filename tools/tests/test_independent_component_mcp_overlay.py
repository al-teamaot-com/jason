from pathlib import Path
import hashlib
import json
import os

import pytest

from tools import independent_component_mcp_overlay as m


BASE = (
    "from jason_mcp.release_approval_request import queue_release_approval_request\n"
    "x = 1\n"
    "\n@mcp.tool()\ndef authorize_pmv4_shadow_release():\n    return 1\n"
)
REVIEWED = BASE.replace(
    m.IMPORT_ANCHOR, m.IMPORT_ANCHOR + m.NEW_IMPORT,
).replace(
    m.ENDPOINT_ANCHOR,
    "\n@mcp.tool()\ndef approve_independent_component_release():\n"
    "    return queue_component_release_approval()\n" + m.ENDPOINT_ANCHOR,
)


def test_exact_narrow_patch_without_unrelated_server_changes(monkeypatch):
    monkeypatch.setattr(m, "BASE_SERVER_SHA256", m.sha(BASE.encode()))
    patched = m.exact_patch(BASE.encode(), REVIEWED.encode())
    assert patched.decode() == REVIEWED
    assert patched.count(b"approve_independent_component_release") == 1
    assert BASE.encode() != patched


def test_baseline_hash_mismatch_denied():
    with pytest.raises(m.MCPOverlayDenied, match="HASH_MISMATCH"):
        m.exact_patch(b"other baseline", REVIEWED.encode())


def test_import_or_endpoint_preexistence_denied(monkeypatch):
    monkeypatch.setattr(m, "BASE_SERVER_SHA256", m.sha(REVIEWED.encode()))
    with pytest.raises(m.MCPOverlayDenied, match="ANCHOR_CONFLICT"):
        m.exact_patch(REVIEWED.encode(), REVIEWED.encode())


def test_unreviewed_source_commit_denied(tmp_path):
    with pytest.raises(m.MCPOverlayDenied, match="SOURCE_SHA_NOT_REVIEWED"):
        m.git_blob(tmp_path, "0" * 40, m.SERVER_PATH)


def test_destination_rejects_parent_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ROOT", tmp_path)
    with pytest.raises(m.MCPOverlayDenied, match="DESTINATION_UNSAFE"):
        m.safe_destination(tmp_path.parent / "untrusted")
    with pytest.raises(m.MCPOverlayDenied, match="DESTINATION_UNSAFE"):
        m.safe_destination(tmp_path / ".." / "escape")


def test_stage_verify_and_tamper_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "staging"
    root.mkdir()
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "BASE_SERVER_SHA256", m.sha(BASE.encode()))
    monkeypatch.setattr(m, "git_blob", lambda repo, sha, path: (
        REVIEWED.encode() if path == m.SERVER_PATH
        else b"def queue_component_release_approval():\n    return 1\n"
    ))
    baseline = tmp_path / "baseline.py"
    baseline.write_bytes(BASE.encode())
    dest = root / "candidate"
    record = m.stage(tmp_path, baseline, dest, verify_only=False)
    assert record["status"] == "verified"
    assert record["production_installed"] is False
    assert m.stage(tmp_path, baseline, dest, verify_only=True) == record
    payload = json.loads((dest / "source-overlay.json").read_text())
    assert payload["base_image_id"] == m.BASE_IMAGE_ID
    assert b"FROM ${BASE_IMAGE}" in (dest / "Dockerfile").read_bytes()
    (dest / "server.py").chmod(0o600)
    (dest / "server.py").write_bytes(b"tampered")
    with pytest.raises(m.MCPOverlayDenied, match="STAGED_BYTES_DRIFTED"):
        m.stage(tmp_path, baseline, dest, verify_only=True)


def test_staged_module_is_not_root_policy_or_production_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BASE_SERVER_SHA256", m.sha(BASE.encode()))
    monkeypatch.setattr(m, "git_blob", lambda repo, sha, path: (
        REVIEWED.encode() if path == m.SERVER_PATH else b"pass\n"
    ))
    baseline = tmp_path / "baseline.py"
    baseline.write_bytes(BASE.encode())
    files = m.staged_files(tmp_path, baseline)
    assert sorted(files) == ["Dockerfile", "independent_component_release_approval.py", "server.py"]
    assert b"docker compose up" not in files["Dockerfile"]
    assert b"RUN chmod" in files["Dockerfile"]

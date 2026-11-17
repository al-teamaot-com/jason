"""Postmigration Ticket Core handoff cannot remigrate data or mint authority."""
from pathlib import Path
import json
import os
import subprocess

import pytest

from tools import pmv4_c_canonical_resume_root as root
from tools import pmv4_c_canonical_resume_builder as builder
from tools import pmv4_c_canonical_resume_owner as owner


def test_new_exact_action_one_owner_and_runtime_restart_only():
    assert root.ACTION == owner.ACTION == "pmv4-c-one-owner-existing-canonical-worker-handoff-v1"
    assert root.ACTION != root.c.ACTION
    script = Path(root.__file__).read_text()
    assert "move_under_signed_root(" not in script
    assert "rollback_before_new_writer(" not in script
    assert "docker\", \"rename\", \"jason-mcp-pilot" not in script
    assert "JASON_TICKET_WORKER_HOSTING" in script


def test_canonical_packet_requires_prior_same_inode_and_no_old_file(tmp_path, monkeypatch):
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    ticket = tmp_path / "ticket-core"
    ticket.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    key = "autonomy-operational-work.sqlite3"
    new = ticket / key
    new.write_bytes(b"synthetic")
    new.chmod(0o600)
    meta = new.stat()
    # CI runners may be UID 1001; simulate the exact production UID 1000
    # for this fixture without privilege or mutation to a real Jason inode.
    from types import SimpleNamespace
    original_lstat = Path.lstat
    def synthetic_lstat(path):
        stat_result = original_lstat(path)
        if path == new:
            return SimpleNamespace(
                st_mode=stat_result.st_mode, st_uid=1000, st_gid=1000,
                st_ino=stat_result.st_ino, st_dev=stat_result.st_dev,
                st_nlink=stat_result.st_nlink,
            )
        return stat_result
    monkeypatch.setattr(Path, "lstat", synthetic_lstat)
    prior = {
        "candidate_sha": root.PREVIOUS,
        "production_lkg_sha": "a" * 40,
        "db_identities": {
            str(old_dir / key): {
                "device": meta.st_dev, "inode": meta.st_ino,
                "mode": 0o600, "uid": os.geteuid(), "gid": os.getegid(),
            }
        },
        "runtime_image_digest": "sha256:"+"1"*64,
        "mcp_image_digest": "sha256:"+"2"*64,
        "worker_image_digest": "sha256:"+"3"*64,
        "watchdog_base_sha256": "4"*64,
        "watchdog_candidate_sha256": "5"*64,
        "service_manifest_sha256": "6"*64,
    }
    prior_dir = tmp_path / ("pmv4-c-" + root.PREVIOUS)
    prior_dir.mkdir()
    (prior_dir / "root-release-plan.json").write_bytes(root.c.canon(prior))
    (prior_dir / "root-oneowner-proof.json").write_text("synthetic")
    monkeypatch.setattr(root, "PRIOR", prior_dir)
    monkeypatch.setattr(root, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(root.c, "TICKET_TARGET", ticket)
    monkeypatch.setattr(root.c, "SHARED_TARGET", shared)
    monkeypatch.setattr(root.os, "geteuid", lambda: 0)
    sha = "b"*40
    path = tmp_path / ("pmv4-c-resume-" + sha)
    path.mkdir()
    data = {
        "schema_version": "1.0", "action": root.ACTION,
        "candidate_sha": sha, "rollback_sha": prior["production_lkg_sha"],
        "production_lkg_sha": prior["production_lkg_sha"],
        "runtime_image_digest": prior["runtime_image_digest"],
        "mcp_image_digest": prior["mcp_image_digest"],
        "worker_image_digest": prior["worker_image_digest"],
        "watchdog_base_sha256": prior["watchdog_base_sha256"],
        "watchdog_candidate_sha256": prior["watchdog_candidate_sha256"],
        "service_manifest_sha256": prior["service_manifest_sha256"],
        "previous_plan_sha256": root.c.sha((prior_dir/"root-release-plan.json").read_bytes()),
        "previous_proof_sha256": root.c.sha((prior_dir/"root-oneowner-proof.json").read_bytes()),
        "owner_consents": 1, "standing_authority": False,
        "later_stages_authorized": False, "no_database_relocation": True,
        "service_restarts": ["jason-runtime"],
        "two_scan_acceptance": True,
    }
    def save():
        tosign = dict(data)
        tosign.pop("scope_sha256", None)
        data["scope_sha256"] = root.c.sha(root.c.canon(tosign))
        (path/"root-release-plan.json").write_bytes(root.c.canon(data))
    save()
    assert root.packet(path/"root-release-plan.json")[1] == prior
    (old_dir/key).write_bytes(b"unapproved legacy duplicate")
    with pytest.raises(root.c.StageCRootDenied, match="CANONICAL_INODE_CHANGED"):
        root.packet(path/"root-release-plan.json")
    (old_dir/key).unlink()
    data["service_restarts"] = ["jason-runtime", "jason-mcp-pilot"]
    save()
    with pytest.raises(root.c.StageCRootDenied, match="SCOPE_INVALID"):
        root.packet(path/"root-release-plan.json")
    data["service_restarts"] = ["jason-runtime"]
    data["watchdog_candidate_sha256"] = "f"*64
    save()
    with pytest.raises(root.c.StageCRootDenied, match="UNREVIEWED_PREVIOUS_RESOURCE_SCOPE"):
        root.packet(path/"root-release-plan.json")


def test_proposed_local_launcher_is_syntax_valid_and_requires_interactive_owner(tmp_path):
    candidate = tmp_path/("pmv4-c-resume-" + "b"*40)
    text = builder.launcher(candidate, {"tools/pmv4_c_atomic_root.py": "x"*64})
    script = tmp_path/"launcher.sh"
    script.write_text(text)
    result = subprocess.run(["/bin/bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "INTERACTIVE_OWNER_TTY_REQUIRED" in text
    assert "--preflight" in text and "--authorize" in text
    assert text.index(" --preflight\n") < text.index(" --authorize\n") < text.index(" --execute\n")
    assert "PRODUCTION_MUTATIONS=false" in text

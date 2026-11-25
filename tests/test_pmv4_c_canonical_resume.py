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
    source_policy = {
        "schema_version": "1.0",
        "allowed_running_containers": [],
        "allowed_system_units": ["jason-boot-recovery.service"],
        "max_stopped_rollback_containers": 20,
    }
    baseline = (json.dumps(source_policy, sort_keys=True, indent=2) + "\n").encode()
    (prior_dir / "production-desired-state.base.json").write_bytes(baseline)
    stage_c_policy = dict(source_policy)
    stage_c_policy["allowed_running_containers"] = [root.c.WORKER]
    old_target = (json.dumps(stage_c_policy, sort_keys=True, indent=2) + "\n").encode()
    (prior_dir / "production-desired-state.stage-c.json").write_bytes(old_target)
    prior["watchdog_base_sha256"] = root.c.sha(baseline)
    prior["watchdog_candidate_sha256"] = root.c.sha(old_target)
    (prior_dir / "root-release-plan.json").write_bytes(root.c.canon(prior))
    (prior_dir / "root-oneowner-proof.json").write_text("synthetic")

    catalog_dir = tmp_path / ("pmv4-catalog-drift-" + root.CATALOG_SOURCE)
    catalog_dir.mkdir()
    approved_policy = dict(source_policy)
    approved_policy["allowed_system_units"] = sorted(
        source_policy["allowed_system_units"] + list(root.CATALOG_UNITS))
    approved = (json.dumps(approved_policy, sort_keys=True, indent=2) + "\n").encode()
    (catalog_dir / "baseline.json").write_bytes(baseline)
    (catalog_dir / "candidate.json").write_bytes(approved)
    catalog_plan = {
        "action": "pmv4-catalog-four-unit-drift-policy-reconcile-v1",
        "source_sha": root.CATALOG_SOURCE,
        "candidate_sha": root.CATALOG_SOURCE,
        "rollback_sha": prior["production_lkg_sha"],
        "catalog_unit_names": list(root.CATALOG_UNITS),
        "baseline_policy_sha256": root.c.sha(baseline),
        "candidate_policy_sha256": root.c.sha(approved),
        "owner_consents": 1,
        "restart_containers": [],
    }
    catalog_plan["scope_sha256"] = root.c.sha(root.c.canon(catalog_plan))
    (catalog_dir / "root-release-plan.json").write_bytes(root.c.canon(catalog_plan))
    catalog_proof = {
        "action": catalog_plan["action"],
        "source_sha": root.CATALOG_SOURCE,
        "scope_sha256": catalog_plan["scope_sha256"],
        "plan_sha256": root.c.sha(root.c.canon(catalog_plan)),
        "approval_id": "test-root-signed-owner",
        "signed_release": {"test": True},
    }
    (catalog_dir / "root-oneowner-proof.json").write_bytes(root.c.canon(catalog_proof))
    audit_dir = tmp_path / "catalog-accepted"
    audit_dir.mkdir()
    receipt = {
        "status": "four_unit_catalog_policy_reconciled",
        "action": catalog_plan["action"],
        "source_sha": root.CATALOG_SOURCE,
        "owner_approval_id": catalog_proof["approval_id"],
        "candidate_policy_sha256": root.c.sha(approved),
        "breaker_override": False,
        "ticket_core_restarts": 0,
        "mcp_restarts": 0,
    }
    (audit_dir / (root.CATALOG_SOURCE + "-accepted.json")).write_bytes(root.c.canon(receipt))
    monkeypatch.setattr(root, "CATALOG_PACKET", catalog_dir)
    monkeypatch.setattr(root, "CATALOG_AUDIT", audit_dir)
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
        "watchdog_base_sha256": root.c.sha(approved),
        "watchdog_candidate_sha256": root.c.sha(root.reviewed_candidate_policy(approved)),
        "catalog_policy_source_sha": root.CATALOG_SOURCE,
        "catalog_policy_proof_sha256": root.c.sha(
            (catalog_dir / "root-oneowner-proof.json").read_bytes()),
        "catalog_policy_sha256": root.c.sha(approved),
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
    receipt_path = audit_dir / (root.CATALOG_SOURCE + "-accepted.json")
    approved_receipt = receipt_path.read_bytes()
    changed = dict(receipt)
    changed["candidate_policy_sha256"] = "0" * 64
    receipt_path.write_bytes(root.c.canon(changed))
    with pytest.raises(root.c.StageCRootDenied,
                       match="CATALOG_PRIOR_ROOT_ACCEPTANCE_NOT_PROVEN"):
        root.packet(path/"root-release-plan.json")
    receipt_path.write_bytes(approved_receipt)
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


def test_handoff_only_recreates_runtime_and_starts_existing_worker(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    class Host:
        @contextmanager
        def host_release_transaction(self):
            yield
        def _assert_protected_release_state(self):
            pass

    sha = "b" * 40
    db = tmp_path / "watchdog.json"
    db.write_text("baseline")
    candidate = tmp_path / ("pmv4-c-resume-" + sha)
    candidate.mkdir()
    (candidate / "service-manifest.json").write_text("{}")
    (candidate / "watchdog-candidate.json").write_text("allowed-stage-c")
    plan = {
        "candidate_sha": sha, "worker_image_digest": "sha256:" + "a"*64,
        "mcp_container_id": "mcp-untouched",
        "watchdog_candidate_sha256": root.c.sha(b"allowed-stage-c"),
    }
    events = []
    monkeypatch.setattr(root, "preflight", lambda path: (plan, Host()))
    monkeypatch.setattr(root, "verify_owner", lambda *a, **kw: "exact-owner-1")
    monkeypatch.setattr(root.c, "read_json", lambda path: {})
    monkeypatch.setattr(root.c, "_clone_command",
                        lambda *a, **kw: (["docker", "create-runtime"], None, []))
    monkeypatch.setattr(root.c, "_worker_create",
                        lambda *a, **kw: ["docker", "create-worker"])
    monkeypatch.setattr(root.c, "_wait_ticket_idle",
                        lambda *a, **kw: ("cycle-before", "2026-11-17T20:00:00+00:00"))
    monkeypatch.setattr(root.c, "_ensure_root_state", lambda: None)
    monkeypatch.setattr(root.c, "WATCHDOG", db)
    monkeypatch.setattr(root.c, "_stop", lambda n: events.append(("stop", n)))
    monkeypatch.setattr(root.c, "_run", lambda args, **kw: events.append(tuple(args)))
    monkeypatch.setattr(root.c, "_connect_and_start",
                        lambda name, nets, **kw: events.append(("start", name)))
    monkeypatch.setattr(root.c, "_wait_container",
                        lambda name, **kw: {"Id": name})
    monkeypatch.setattr(root.c, "_docker_json",
                        lambda name: {"Id": "mcp-untouched"} if name == "jason-mcp-pilot" else {})
    monkeypatch.setattr(root.c, "_append",
                        lambda plan, owner, event, detail: events.append(("audit", event)))
    monkeypatch.setattr(root.service, "validate_effective_inspect",
                        lambda *args: None)
    monkeypatch.setattr(root.c, "_atomic_policy",
                        lambda contents, meta: db.write_bytes(contents))
    root.execute(candidate / "root-release-plan.json")
    assert ("stop", "jason-runtime") in events
    assert ("stop", "jason-mcp-pilot") not in events
    assert ("/usr/bin/docker", "start", "jason-pmv4-ticket-core") in events
    assert ("audit", "activated") in events
    assert db.read_text() == "allowed-stage-c"
    assert not any(row and row[0] in ("/usr/bin/mv", "mv") for row in events)


def test_failure_attempts_same_canonical_data_rollback(tmp_path, monkeypatch):
    # The rollback is the existing embedded worker, not an old SQLite copy.
    from contextlib import contextmanager
    from types import SimpleNamespace
    class Host:
        @contextmanager
        def host_release_transaction(self):
            yield
        def _assert_protected_release_state(self): pass
    sha = "c"*40
    packet = tmp_path / ("pmv4-c-resume-" + sha)
    packet.mkdir()
    (packet / "watchdog-candidate.json").write_bytes(b"approved-candidate")
    path = packet / "root-release-plan.json"
    policy = tmp_path / "watchdog.json"
    policy.write_bytes(b"old-base")
    calls = []
    plan = {"candidate_sha": sha, "mcp_container_id": "unchanged",
            "watchdog_candidate_sha256": root.c.sha(b"approved-candidate")}
    monkeypatch.setattr(root, "preflight", lambda *a: (plan, Host()))
    monkeypatch.setattr(root, "verify_owner", lambda *a, **kw: "owner-1")
    monkeypatch.setattr(root.c, "read_json", lambda *a: {})
    monkeypatch.setattr(root.c, "_clone_command",
                        lambda *a, **kw: (["docker", "create-runtime"], None, []))
    monkeypatch.setattr(root.c, "_worker_create", lambda *a: ["docker", "create-worker"])
    monkeypatch.setattr(root.c, "_wait_ticket_idle", lambda *a: ("before", "time"))
    monkeypatch.setattr(root.c, "_ensure_root_state", lambda: None)
    monkeypatch.setattr(root.c, "WATCHDOG", policy)
    monkeypatch.setattr(root.c, "_stop", lambda n: calls.append(("stop", n)))
    def run(args, **kwargs):
        calls.append(tuple(args))
        if args[-2:] == ["start", root.c.WORKER]:
            raise RuntimeError("SYNTHETIC_WORKER_START_FAILURE")
    monkeypatch.setattr(root.c, "_run", run)
    monkeypatch.setattr(root.c, "_connect_and_start", lambda *a, **kw: None)
    monkeypatch.setattr(root.c, "_wait_container", lambda *a, **kw: {})
    monkeypatch.setattr(root.c, "_append", lambda *a: None)
    monkeypatch.setattr(root.c, "_atomic_policy",
                        lambda contents, meta: policy.write_bytes(contents))
    rollback = []
    monkeypatch.setattr(root, "rollback",
                        lambda p, a, *, policy_changed: rollback.append(policy_changed))
    with pytest.raises(RuntimeError, match="SYNTHETIC_WORKER_START_FAILURE"):
        root.execute(path)
    assert rollback == [True]
    assert ("stop", "jason-mcp-pilot") not in calls



def test_original_worker_and_catalog_policy_join_exactly(tmp_path, monkeypatch):
    original = {
        "schema_version": "1.0",
        "allowed_running_containers": ["jason-runtime"],
        "allowed_system_units": ["jason-boot-recovery.service"],
        "required_containers": ["jason-runtime", "jason-mcp-pilot"],
        "max_stopped_rollback_containers": 20,
        "forbidden_execution_prefixes": ["/unsafe"],
    }
    stage_c = dict(original)
    stage_c["allowed_running_containers"] = ["jason-runtime", root.c.WORKER]
    stage_data = (json.dumps(stage_c, indent=2, sort_keys=True) + "\n").encode()
    prior_dir = tmp_path / "stage-c-source"
    prior_dir.mkdir()
    (prior_dir / "production-desired-state.base.json").write_text(
        json.dumps(original, indent=2, sort_keys=True) + "\n")
    (prior_dir / "production-desired-state.stage-c.json").write_bytes(stage_data)
    monkeypatch.setattr(root, "PRIOR", prior_dir)
    monkeypatch.setattr(root, "original",
                        lambda: {"watchdog_candidate_sha256": root.c.sha(stage_data)})
    catalog = dict(original)
    catalog["allowed_system_units"] = sorted(
        original["allowed_system_units"] + list(root.CATALOG_UNITS))
    approved = (json.dumps(catalog, indent=2, sort_keys=True) + "\n").encode()
    adjusted = json.loads(root.reviewed_candidate_policy(approved))
    assert adjusted["max_stopped_rollback_containers"] == 21
    assert adjusted["allowed_running_containers"] == ["jason-runtime", root.c.WORKER]
    assert adjusted["allowed_system_units"] == catalog["allowed_system_units"]
    assert {k: v for k, v in adjusted.items()
            if k not in ("max_stopped_rollback_containers", "allowed_running_containers")} == {
                k: v for k, v in catalog.items()
                if k not in ("max_stopped_rollback_containers", "allowed_running_containers")}
    catalog["max_stopped_rollback_containers"] = 21
    with pytest.raises(root.c.StageCRootDenied, match="CATALOG_STAGE_C_BASELINE_UNEXPECTED"):
        root.reviewed_candidate_policy(json.dumps(catalog).encode())
    catalog["max_stopped_rollback_containers"] = 20
    catalog["allowed_running_containers"] = ["jason-runtime", root.c.WORKER]
    with pytest.raises(root.c.StageCRootDenied, match="CATALOG_STAGE_C_BASELINE_UNEXPECTED"):
        root.reviewed_candidate_policy(json.dumps(catalog).encode())
    catalog["allowed_running_containers"] = ["jason-runtime"]
    catalog["allowed_system_units"].remove(root.CATALOG_UNITS[0])
    with pytest.raises(root.c.StageCRootDenied, match="CATALOG_STAGE_C_BASELINE_UNEXPECTED"):
        root.reviewed_candidate_policy(json.dumps(catalog).encode())

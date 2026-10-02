from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools.full_recovery_restore import (
    INTERNAL_MANIFEST_MEMBER,
    RecoveryRestoreError,
    acknowledge_reenrollment,
    apply_recovery_restore_plan,
    assemble_recovery_members,
    plan_recovery_restore,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ID = "a" * 64


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def inventory():
    return load("config/recovery-state-inventory.v1.json")


def schema():
    return load("config/schemas/full-recovery-payload-manifest.schema.json")


def normal_members():
    return assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=(
            (
                "deployment-configuration",
                "state/deployment/config.json",
                "etc/jason/deployment.json",
                b'{"environment":"candidate"}',
                {"source": "synthetic"},
            ),
            (
                "authority-and-identity",
                "state/authority/authority.sqlite3",
                "var/lib/jason/authority/authority.sqlite3",
                b"synthetic-authority-snapshot",
                {"consistency": "sqlite"},
            ),
            (
                "provider-secrets",
                "secrets/providers/provider-token",
                "var/lib/jason/recovery-secrets/provider-token",
                b"synthetic-secret",
                {"provider": "synthetic"},
            ),
        ),
        metadata_only=(
            (
                "service-and-schedule-definitions",
                {"source": "release"},
            ),
        ),
    )


def test_restore_plan_validates_payloads_before_writes(tmp_path):
    members = normal_members()
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert plan.status == "ready_for_restore"
    assert plan.destructive_restore_performed is False
    assert [a.action for a in plan.actions].count("restore") == 3
    assert [a.action for a in plan.actions].count("reconstruct") == 1
    assert not (tmp_path / "restored").exists()


def test_restore_apply_writes_only_planned_payloads_with_private_permissions(tmp_path):
    members = normal_members()
    root = tmp_path / "restored"
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=root,
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    result = apply_recovery_restore_plan(
        plan=plan,
        decrypted_members=members,
    )
    assert result["status"] == "restore_payload_applied"
    assert result["services_started"] is False
    assert result["migrations_run"] is False
    secret = root / "var/lib/jason/recovery-secrets/provider-token"
    assert secret.read_bytes() == b"synthetic-secret"
    assert (secret.stat().st_mode & 0o777) == 0o600


def test_digest_tampering_blocks_before_restore(tmp_path):
    members = normal_members()
    tampered = dict(members)
    tampered["state/authority/authority.sqlite3"] = b"tampered"
    plan = plan_recovery_restore(
        decrypted_members=tampered,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert plan.status == "blocked"
    assert any(item.startswith("payload_") for item in plan.blockers)
    with pytest.raises(PermissionError, match="not ready"):
        apply_recovery_restore_plan(plan=plan, decrypted_members=tampered)


def test_unmanifested_payload_blocks_restore(tmp_path):
    members = normal_members()
    members["state/mystery.bin"] = b"mystery"
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert "unmanifested_payload:state/mystery.bin" in plan.blockers


def test_machine_bound_identity_stops_for_reenrollment(tmp_path):
    members = assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=(),
        metadata_only=(
            (
                "host-bound-identity",
                {"identity": "synthetic-tpm-registration"},
            ),
        ),
    )
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert plan.status == "blocked_for_reenrollment"
    assert "reenrollment_required:host-bound-identity" in plan.blockers


def test_machine_bound_payload_is_rejected_even_if_manifest_is_tampered(tmp_path):
    members = normal_members()
    manifest = json.loads(members[INTERNAL_MANIFEST_MEMBER])
    payload = b"machine-secret"
    name = "state/machine/private-key"
    members[name] = payload
    manifest["entries"].append(
        {
            "state_class": "host-bound-identity",
            "member_name": name,
            "restore_relative_path": "var/lib/jason/machine/private-key",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "source_metadata": {},
        }
    )
    members[INTERNAL_MANIFEST_MEMBER] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert "state_class_not_exportable:host-bound-identity" in plan.blockers


def test_source_deployment_identity_mismatch_blocks_restore(tmp_path):
    members = normal_members()
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256="b" * 64,
    )
    assert "source_deployment_identity_mismatch" in plan.blockers


def test_existing_target_file_causes_apply_to_fail_closed(tmp_path):
    members = normal_members()
    root = tmp_path / "restored"
    existing = root / "etc/jason/deployment.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing")
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=root,
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    with pytest.raises(RecoveryRestoreError, match="already exists"):
        apply_recovery_restore_plan(
            plan=plan,
            decrypted_members=members,
        )
    assert existing.read_text() == "existing"


def test_live_root_is_not_a_supported_restore_target():
    with pytest.raises(PermissionError, match="live filesystem root"):
        plan_recovery_restore(
            decrypted_members=normal_members(),
            state_inventory=inventory(),
            payload_manifest_schema=schema(),
            target_root="/",
            expected_source_deployment_identity_sha256=SOURCE_ID,
        )


def test_reenrollment_acknowledgement_clears_only_named_reenrollment_blockers(tmp_path):
    members = assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=(),
        metadata_only=(
            ("host-bound-identity", {"identity": "synthetic-tpm-registration"}),
        ),
    )
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert plan.status == "blocked_for_reenrollment"
    ready = acknowledge_reenrollment(
        plan=plan,
        completed_state_classes=("host-bound-identity",),
    )
    assert ready.status == "ready_for_restore"
    assert ready.blockers == ()
    assert all(action.action != "reenroll" for action in ready.actions)


def test_reenrollment_acknowledgement_rejects_unrequested_state_class(tmp_path):
    members = assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=(),
        metadata_only=(
            ("host-bound-identity", {"identity": "synthetic-tpm-registration"}),
        ),
    )
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory(),
        payload_manifest_schema=schema(),
        target_root=tmp_path / "restored",
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    with pytest.raises(RecoveryRestoreError, match="not required"):
        acknowledge_reenrollment(
            plan=plan,
            completed_state_classes=("provider-secrets",),
        )

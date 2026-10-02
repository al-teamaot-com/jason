from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.production_promotion_gate import (
    evaluate_production_promotion,
    promotion_plan_sha256,
)
from tools import deploy_live_container as deploy
from orchestrator.production_promotion_permit import (
    ProductionPromotionPermitError,
    ProductionPromotionPermitIssuer,
    ProductionPromotionPermitVerifier,
    SQLiteProductionPromotionPermitClaims,
)
from orchestrator.production_promotion_approval import ProductionPromotionAuthorization

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


NOW = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)
OWNER = "owner:al"
SOURCE = "a" * 40
ARTIFACT = "sha256:" + "b" * 64


def identity(source: str = SOURCE, artifact: str = ARTIFACT):
    return {
        "release_version": "1.0.0-rc1",
        "source_sha": source,
        "artifact_digest": artifact,
        "configuration_revision": "c" * 64,
        "policy_revision": "d" * 64,
        "playbook_revision": "e" * 64,
        "schema_revision": "f" * 64,
    }


def plan():
    return {
        "schema_version": "1.0",
        "promotion_id": "promotion-acceptance-1",
        "target_environment": "production",
        "current": identity("1" * 40, "sha256:" + "2" * 64),
        "target": identity(),
        "affected_components": ["jason-runtime"],
        "configuration_changes": [],
        "policy_changes": [],
        "migrations": [],
        "expected_service_impact": "none expected",
        "preflight_evidence": ["preflight-acceptance"],
        "verification": {"checks": ["manifest", "health", "governance"]},
        "rollback": {
            "target": identity("1" * 40, "sha256:" + "2" * 64),
            "state_restore_required": False,
            "method": "restore prior immutable container",
        },
        "blockers": [],
    }


def approval(exact_plan):
    return {
        "schema_version": "1.0",
        "approval_id": "approval-acceptance-1",
        "promotion_id": exact_plan["promotion_id"],
        "target_environment": "production",
        "plan_sha256": promotion_plan_sha256(exact_plan),
        "decision": "approved",
        "approver_principal_id": OWNER,
        "approver_authority": "owner",
        "approved_at": "2026-10-02T15:55:00Z",
        "expires_at": "2026-10-02T16:30:00Z",
        "state": "approved",
        "authority_record_id": "authority-acceptance-1",
    }


def test_no_approval_fails_closed():
    result = evaluate_production_promotion(
        plan=plan(),
        approval=None,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "OWNER_APPROVAL_MISSING" in result.reason_codes


def test_wrong_approver_fails_closed():
    candidate = plan()
    accepted = approval(candidate)
    accepted["approver_principal_id"] = "technician:someone"
    result = evaluate_production_promotion(
        plan=candidate,
        approval=accepted,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVER_NOT_TRUSTED" in result.reason_codes


def test_wrong_environment_fails_closed():
    candidate = plan()
    accepted = approval(candidate)
    candidate["target_environment"] = "candidate"
    accepted["plan_sha256"] = promotion_plan_sha256(candidate)
    result = evaluate_production_promotion(
        plan=candidate,
        approval=accepted,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "TARGET_NOT_PRODUCTION" in result.reason_codes


def test_expired_approval_fails_closed():
    candidate = plan()
    accepted = approval(candidate)
    accepted["expires_at"] = "2026-10-02T15:59:59Z"
    result = evaluate_production_promotion(
        plan=candidate,
        approval=accepted,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVAL_EXPIRED" in result.reason_codes


def test_changed_material_after_approval_changes_plan_fingerprint_and_fails_closed():
    original = plan()
    accepted = approval(original)

    mutations = []
    for label, mutate in (
        ("source", lambda x: x["target"].__setitem__("source_sha", "9" * 40)),
        ("artifact", lambda x: x["target"].__setitem__("artifact_digest", "sha256:" + "8" * 64)),
        ("configuration", lambda x: x["target"].__setitem__("configuration_revision", "7" * 64)),
        ("policy", lambda x: x["target"].__setitem__("policy_revision", "6" * 64)),
        ("playbook", lambda x: x["target"].__setitem__("playbook_revision", "5" * 64)),
        ("schema", lambda x: x["target"].__setitem__("schema_revision", "4" * 64)),
        ("migration", lambda x: x["migrations"].append({
            "id": "migration-1",
            "source_version": "1",
            "target_version": "2",
            "reversible": False,
            "backup_required": True,
        })),
    ):
        changed = deepcopy(original)
        mutate(changed)
        mutations.append((label, changed))

    for label, changed in mutations:
        assert promotion_plan_sha256(changed) != accepted["plan_sha256"], label
        result = evaluate_production_promotion(
            plan=changed,
            approval=accepted,
            trusted_owner_principals={OWNER},
            now=NOW,
        )
        assert result.allowed is False, label
        assert "APPROVAL_PLAN_MISMATCH" in result.reason_codes, label


def test_unresolved_blocker_fails_closed_even_with_matching_approval():
    candidate = plan()
    candidate["blockers"] = ["backup checkpoint missing"]
    accepted = approval(candidate)
    result = evaluate_production_promotion(
        plan=candidate,
        approval=accepted,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "UNRESOLVED_BLOCKERS" in result.reason_codes


def permit_fixture():
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    public_pem = private.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    candidate = plan()
    authorization = ProductionPromotionAuthorization(
        approval_id="approval-acceptance-1",
        promotion_id=candidate["promotion_id"],
        plan_sha256=promotion_plan_sha256(candidate),
        authority_context_id="context-acceptance-1",
        decided_by=OWNER,
        expires_at=NOW + timedelta(minutes=20),
    )
    issuer = ProductionPromotionPermitIssuer(
        private_key_pem=private_pem,
        signer_key_id="acceptance-key",
    )
    permit = issuer.issue(
        authorization=authorization,
        component="jason-runtime",
        operation="deploy",
        source_sha=SOURCE,
        artifact_digest=ARTIFACT,
        now=NOW,
    )
    return candidate, permit, public_pem


def test_unavailable_trusted_authority_fails_closed():
    candidate, permit, _ = permit_fixture()
    verifier = ProductionPromotionPermitVerifier(public_keys={})
    with pytest.raises(ProductionPromotionPermitError, match="not trusted"):
        verifier.verify(
            permit,
            component="jason-runtime",
            operation="deploy",
            source_sha=SOURCE,
            artifact_digest=ARTIFACT,
            plan_sha256=promotion_plan_sha256(candidate),
            now=NOW + timedelta(minutes=1),
        )


def test_replayed_permit_is_rejected_durably(tmp_path):
    _, permit, _ = permit_fixture()
    claims = SQLiteProductionPromotionPermitClaims(str(tmp_path / "claims.sqlite3"))
    claims.initialize()
    claims.claim(permit, now=NOW + timedelta(minutes=1))
    reopened = SQLiteProductionPromotionPermitClaims(str(tmp_path / "claims.sqlite3"))
    with pytest.raises(ProductionPromotionPermitError, match="already been consumed"):
        reopened.claim(permit, now=NOW + timedelta(minutes=2))


def test_failure_after_approval_consumption_does_not_silently_release_for_retry(tmp_path):
    from orchestrator.approval_continuation_guard import (
        ApprovalContinuationClaim,
        SQLiteApprovalContinuationGuard,
    )

    guard = SQLiteApprovalContinuationGuard(str(tmp_path / "continuations.sqlite3"))
    guard.initialize()
    claim = ApprovalContinuationClaim(
        approval_id="approval-consumed-before-apply",
        organization_id="org-a",
        request_id="promotion-exec-1",
        correlation_id="promotion-corr-1",
        capability="jason.deployment.apply",
        authority_context_id="context-1",
        claimed_at=NOW,
    )
    guard.claim(claim)

    reopened = SQLiteApprovalContinuationGuard(str(tmp_path / "continuations.sqlite3"))
    with pytest.raises(PermissionError, match="already been consumed"):
        reopened.claim(claim)


def test_direct_runner_without_permit_cannot_mutate(monkeypatch, tmp_path):
    existing = tmp_path / "existing"
    existing.write_text("state", encoding="utf-8")
    live = {
        "Id": "live-id",
        "Image": "sha256:" + "1" * 64,
        "Config": {
            "Env": ["JASON_SOURCE_REVISION=" + "1" * 40],
            "User": "1000:1000",
            "WorkingDir": "/opt/jason-src",
            "Labels": {"com.teamaot.jason.source_revision": "1" * 40},
            "Healthcheck": None,
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "no"},
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=32m"},
            "PortBindings": {},
            "NetworkMode": "jason-core",
            "LogConfig": {"Type": "json-file", "Config": {}},
        },
        "Mounts": [{
            "Type": "bind",
            "Source": str(existing),
            "Destination": "/run/existing",
            "RW": False,
        }],
        "NetworkSettings": {"Networks": {"jason-core": {}}},
    }
    mutations = []
    monkeypatch.setattr(deploy, "_container_exists", lambda name: name == "jason-runtime")
    monkeypatch.setattr(deploy, "_image_id", lambda image: ARTIFACT)
    monkeypatch.setattr(deploy, "_inspect", lambda name: live)
    monkeypatch.setattr(deploy, "_run", lambda *args, **kwargs: mutations.append(args))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_live_container.py",
            "--live", "jason-runtime",
            "--image", "candidate",
            "--rollback", "rollback",
            "--source-revision", SOURCE,
            "--health-url", "http://candidate/healthz",
            "--promotion-component", "jason-runtime",
            "--promotion-plan-sha256", "3" * 64,
        ],
    )
    with pytest.raises(SystemExit, match="Production mutation requires --production-permit"):
        deploy.main()
    assert mutations == []


def test_post_deploy_verification_failure_attempts_safe_rollback(monkeypatch, tmp_path):
    old_image = "sha256:" + "1" * 64
    live_before = {
        "Id": "live-before",
        "Image": old_image,
        "Config": {
            "Env": ["JASON_SOURCE_REVISION=" + "1" * 40],
            "User": "1000:1000",
            "WorkingDir": "/opt/jason-src",
            "Labels": {"com.teamaot.jason.source_revision": "1" * 40},
            "Healthcheck": None,
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "no"},
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=32m"},
            "PortBindings": {},
            "NetworkMode": "jason-core",
            "LogConfig": {"Type": "json-file", "Config": {}},
        },
        "Mounts": [],
        "NetworkSettings": {"Networks": {"jason-core": {}}},
    }
    live_after = deepcopy(live_before)
    live_after.update({"Id": "candidate-live", "Image": ARTIFACT})
    live_after["Config"]["Labels"]["com.teamaot.jason.source_revision"] = SOURCE
    live_after["Config"]["Env"] = ["JASON_SOURCE_REVISION=" + SOURCE]

    inspect_calls = {"count": 0}
    def fake_inspect(name):
        inspect_calls["count"] += 1
        return live_before if inspect_calls["count"] == 1 else live_after

    run_calls = []
    rollback_calls = []
    monkeypatch.setattr(deploy, "_container_exists", lambda name: name == "jason-runtime")
    monkeypatch.setattr(deploy, "_image_id", lambda image: ARTIFACT)
    monkeypatch.setattr(deploy, "_inspect", fake_inspect)
    monkeypatch.setattr(deploy, "_run", lambda cmd, **kwargs: run_calls.append(cmd))
    monkeypatch.setattr(
        deploy,
        "verify_and_claim_production_permit",
        lambda **kwargs: SimpleNamespace(
            permit_id="permit-1",
            approval_id="approval-1",
            promotion_id="promotion-1",
        ),
    )
    monkeypatch.setattr(deploy, "_health", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("health failed")))
    monkeypatch.setattr(
        deploy.subprocess,
        "run",
        lambda cmd, **kwargs: rollback_calls.append(cmd) or SimpleNamespace(returncode=0),
    )
    permit = tmp_path / "permit.json"
    permit.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_live_container.py",
            "--live", "jason-runtime",
            "--image", "candidate",
            "--rollback", "rollback",
            "--source-revision", SOURCE,
            "--health-url", "http://candidate/healthz",
            "--production-permit", str(permit),
            "--promotion-component", "jason-runtime",
            "--promotion-plan-sha256", "3" * 64,
        ],
    )
    with pytest.raises(RuntimeError, match="health failed"):
        deploy.main()
    assert ["docker", "stop", "jason-runtime"] in run_calls
    assert ["docker", "rename", "jason-runtime", "rollback"] in run_calls
    assert ["docker", "rm", "-f", "jason-runtime"] in rollback_calls
    assert ["docker", "rename", "rollback", "jason-runtime"] in rollback_calls
    assert ["docker", "start", "jason-runtime"] in rollback_calls


def test_unsafe_teams_rollback_stops_before_mutation(tmp_path):
    service = tmp_path / "service"
    service.mkdir()
    backup = tmp_path / "compose.backup.yaml"
    backup.write_text("services: {}\n", encoding="utf-8")
    state = service / "cutover-state.env"
    state.write_text(
        "\n".join(
            [
                f"BACKUP_FILE={backup}",
                "BACKUP_SHA256=" + "0" * 64,
                "GATEWAY_SOURCE_SHA=" + SOURCE,
                "OPENCLAW_SERVICE=openclaw-gateway",
                "OPENCLAW_PROJECT=openclaw",
                f"OPENCLAW_COMPOSE_FILE={tmp_path / 'compose.yaml'}",
                f"OPENCLAW_WORKDIR={tmp_path}",
                "GATEWAY_CONTAINER=jason-teams-gateway",
                "PROMOTION_PLAN_SHA256=" + "3" * 64,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script = Path("infrastructure/jason-teams-gateway/rollback-production.sh").resolve()
    completed = subprocess.run(
        ["bash", str(script)],
        env={
            **dict(),
            "PATH": "/usr/bin:/bin",
            "JASON_TEAMS_SERVICE_DIR": str(service),
            "JASON_PRODUCTION_PLAN_SHA256": "3" * 64,
            "JASON_PRODUCTION_ROLLBACK_PERMIT": str(tmp_path / "does-not-matter.json"),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "compose backup digest does not match cutover state" in output

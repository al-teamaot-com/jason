import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "tools" / "release_manager_gate.py"
RUNNER_PATH = ROOT / "tools" / "release_manager_host_runner.py"

gate_spec = importlib.util.spec_from_file_location("release_manager_gate", GATE_PATH)
gate_module = importlib.util.module_from_spec(gate_spec)
assert gate_spec.loader is not None
sys.modules["release_manager_gate"] = gate_module
gate_spec.loader.exec_module(gate_module)

runner_spec = importlib.util.spec_from_file_location(
    "release_manager_host_runner_atomic",
    RUNNER_PATH,
)
runner = importlib.util.module_from_spec(runner_spec)
assert runner_spec.loader is not None
runner_spec.loader.exec_module(runner)

@pytest.fixture(autouse=True)
def existing_retention_preflight_is_independently_tested():
    """Atomic surface tests isolate deployment/rollback from container hygiene.

    Actual manual-promotion retention ordering, Docker safety and error handling
    are covered in test_release_manager_host_runner.py.
    """
    with patch.object(runner, "reconcile_stopped_rollback_retention", return_value=16):
        yield


SHA_A = "a" * 40
SHA_B = "b" * 40
BASELINE_RUNTIME_IMAGE = "sha256:" + "2" * 64
BASELINE_MCP_IMAGE = "sha256:" + "4" * 64
CANDIDATE_RUNTIME_IMAGE = "sha256:" + "1" * 64
CANDIDATE_MCP_IMAGE = "sha256:" + "3" * 64


def record():
    return {
        "schema_version": "2.0",
        "release_id": runner.record_id(SHA_A),
        "state": "production_eligible",
        "rollback_sha": SHA_B,
        "risk_profile": "production_control_core",
        "release_manifest": {
            "candidate_sha": SHA_A,
            "rollback_sha": SHA_B,
            "risk_profile": "production_control_core",
        },
        "release_candidate": {
            "candidate_sha": SHA_A,
            "image": "jason-runtime:test-a",
            "artifact_digest": "sha256:runtime-a",
            "mcp_image": "jason-mcp:test-a",
            "mcp_artifact_digest": "sha256:mcp-a",
        },
        # Exercise real rollback fault injection AFTER the production-input
        # contract gate; no test may bypass that new fail-closed check.
        "preproduction": {
            "acceptance_passed": True,
            "native_deploy_contract_digest": runner.native_deploy_contract_digest({
                "JASON_RUNTIME_PRODUCTION_IMAGE": "jason-runtime:test-a",
                "JASON_MCP_PRODUCTION_IMAGE": "jason-mcp:test-a",
                "JASON_SOURCE_REVISION_OVERRIDE": SHA_A,
                "JASON_RELEASE_MOBILE_APPROVAL_MODE": "owner_reviewed",
            }),
        },
        "history": [],
    }


def alignment(sha):
    return {
        "runtime_revision": sha,
        "mcp_revision": sha,
        "host_revision": sha,
        "host_release": f"/opt/jason/releases/{sha}",
    }


def create_candidate_scripts(candidate_tree: Path) -> None:
    for relative in (
        Path("infrastructure/jason-runtime/production-deploy.sh"),
        Path("infrastructure/jason-mcp/production-deploy.sh"),
    ):
        path = candidate_tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
    policy = candidate_tree / "config/mobile-release-approval-policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_bytes((ROOT / "config/mobile-release-approval-policy.json").read_bytes())


def fake_gate(_repo, _state_root, release, target):
    release["state"] = target
    release.setdefault("history", []).append(
        {"state": target, "gate": "pass"}
    )


@pytest.fixture(autouse=True)
def atomic_release_sandbox(monkeypatch, tmp_path):
    """Exercise the transaction under real gates, with NO host/Docker access.

    The original legacy fixture predated mandatory release manifest and CCC
    attestation and returned without reaching any rollback logic. Keep this
    unit harness aligned with the validated source contract while stubbing
    only the external effects, not the rollback execution path itself.
    """
    live_policy = tmp_path / "live-mobile-release-approval-policy.json"
    live_policy.write_text(json.dumps({
        "schema_version": "1.0",
        "organization_id": "aot",
        "policy_mode": "owner_only_pilot",
        "owner_identity_ids": ["person-al"],
        "allowed_risk_profiles": ["normal"],
        "ttl_seconds": 900,
        "capability": "release.production.approve",
    }) + "\n", encoding="utf-8")
    live_policy.chmod(0o600)
    monkeypatch.setattr(runner, "MOBILE_APPROVAL_POLICY", live_policy)
    monkeypatch.setattr(
        runner, "live_release_mobile_approval_mode",
        lambda runtime: (
            "owner_reviewed" if str((runtime or {}).get("revision") or "") == SHA_A
            else "owner_only_pilot"
        ),
    )
    monkeypatch.setattr(runner, "verify_candidate_on_main", lambda *a: None)
    monkeypatch.setattr(runner, "require_current_protected_release_source", lambda *a: None)
    monkeypatch.setattr(runner, "require_current_manual_scope_review", lambda *a: None)
    monkeypatch.setattr(runner, "run_release_ccc_gate",
                        lambda *a, **k: {"status": "PASS",
                                        "mode": "candidate_transition" if k.get("before_mutation") else "live_certified"})
    monkeypatch.setattr(runner, "controller_identity",
                        lambda *a: {"candidate_controller_digest": "sha256:controlled"})
    monkeypatch.setattr(runner, "verify_controller_identity",
                        lambda *a, **k: {
                            "controller_handoff": "staged_for_next_transaction",
                            "executing_controller_revision": SHA_B,
                            "executing_controller_digest": "sha256:old",
                            "installed_controller_digest": "sha256:controlled",
                        })
    monkeypatch.setattr(runner, "capture_production_manifest", lambda sha: {
        "revision": sha, "observed_at": "2026-10-18T13:50:00+00:00",
        "complete": True, "runtime_image_id": (
            BASELINE_RUNTIME_IMAGE if sha == SHA_B else CANDIDATE_RUNTIME_IMAGE
        ),
        "mcp_image_id": (
            BASELINE_MCP_IMAGE if sha == SHA_B else CANDIDATE_MCP_IMAGE
        ),
    })
    monkeypatch.setattr(runner, "set_last_known_good", lambda *a, **k: None)
    monkeypatch.setattr(runner, "open_circuit_breaker", lambda *a, **k: None)
    monkeypatch.setattr(runner, "save_record", lambda *a: None)
    monkeypatch.setattr(runner, "write_owner_notification_event", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_functional_smoke_tests",
                        lambda sha: {"passed": True, "verified_at": "2026-10-18T13:50:00+00:00"})
    monkeypatch.setattr(runner, "production_drift_evidence",
                        lambda *a: {"problems": [], "observed_at": "2026-10-18T13:50:00+00:00"})
    monkeypatch.setattr(runner, "declared_quickbooks_read_profile", lambda *a: None)
    monkeypatch.setattr(runner, "live_quickbooks_read_profile",
                        lambda *a: sorted(runner.QUICKBOOKS_READ_PROFILES)[0])
    monkeypatch.setattr(runner.worker_enrollment, "approved_diagnostic_uid", lambda *a: "")
    monkeypatch.setattr(runner.worker_enrollment, "live_diagnostic_uid", lambda *a: "")


def test_atomic_deploy_updates_runtime_mcp_host_and_release_manager_before_close():
    with tempfile.TemporaryDirectory() as td:
        state_root = Path(td)
        candidate_tree = state_root / "candidate"
        create_candidate_scripts(candidate_tree)
        events = []

        def image_id(name):
            return {
                "jason-runtime:test-a": "sha256:runtime-a",
                "jason-mcp:test-a": "sha256:mcp-a",
                "jason-runtime:production": "sha256:runtime-a",
                "jason-mcp:production": "sha256:mcp-a",
            }[name]

        def run_command(args, *, cwd=None, env=None):
            command = str(args[0])
            if "jason-runtime" in command:
                events.append("runtime")
            elif "jason-mcp" in command:
                events.append("mcp")
            return "DEPLOYMENT=PASS"

        def host(_state_root, sha, **_kwargs):
            events.append("host:" + sha)
            return {"success": True, "source_revision": sha}

        def manager(sha):
            events.append("manager:" + sha)
            return {
                "source_revision": sha,
                "timer_active": True,
                "source_link": f"/opt/jason/releases/{sha}",
            }

        with (
            patch.object(runner, "image_id", side_effect=image_id),
            patch.object(runner, "require_host_reconciler_ready"),
            patch.object(
                runner,
                "live_production_alignment",
                side_effect=lambda sha: alignment(sha),
            ),
            patch.object(runner, "gate_transition", side_effect=fake_gate),
            patch.object(runner, "worktree", return_value=candidate_tree),
            patch.object(
                runner,
                "verify_candidate_host_reconciliation_contract",
                return_value={
                    "candidate_script_verified": True,
                    "managed_engineering_source_verified": True,
                    "managed_documentation_source_verified": True,
                    "developer_checkout_absent": True,
                },
            ),
            patch.object(
                runner,
                "verify_host_reconciliation_evidence",
                return_value={
                    "candidate_script_verified": True,
                    "managed_engineering_source_verified": True,
                    "managed_documentation_source_verified": True,
                    "developer_checkout_absent": True,
                },
            ),
            patch.object(runner, "remove_worktree"),
            patch.object(runner, "run", side_effect=run_command),
            patch.object(
                runner,
                "wait_live_runtime",
                return_value={"revision": SHA_A},
            ),
            patch.object(
                runner,
                "live_mcp",
                return_value={"revision": SHA_A},
            ),
            patch.object(runner, "request_host_reconcile", side_effect=host),
            patch.object(
                runner,
                "install_release_manager_from_current",
                side_effect=manager,
            ),
            patch.object(runner, "publish_production_closeout") as published,
            patch.object(runner, "write_owner_notification_event") as notified,
            patch.object(runner, "open_circuit_breaker") as breaker,
        ):
            result = runner.deploy_production(ROOT, state_root, record())

        assert result["state"] == "closed"
        assert "failure" not in result
        breaker.assert_not_called()
        # Administrative publication still does not execute within live
        # promotion. Production lifecycle notifications are durable status
        # events and are intentionally emitted independently of publication.
        published.assert_not_called()
        assert [
            call.args[2] for call in notified.call_args_list
        ] == ["production_push_started", "production_push_result"]
        assert (
            notified.call_args_list[-1].kwargs["result_status"]
            == "verified_success"
        )
        assert result["administrative_closeout"]["needs_retry"] is True
        assert result["administrative_closeout"]["documentation_control_board"]["status"] == "pending"
        assert result["administrative_closeout"]["owner_notification"]["status"] == "pending"
        assert result["production"]["documentation_reconciliation"] == "pending"
        assert events[:4] == [
            "runtime",
            "mcp",
            "host:" + SHA_A,
            "manager:" + SHA_A,
        ]
        production = result["production"]
        assert production["alignment_verified"] is True
        assert production["release_manager_timer_active"] is True
        assert production["runtime_revision"] == SHA_A
        assert production["mcp_revision"] == SHA_A
        assert production["host_revision"] == SHA_A


@pytest.mark.parametrize("host_rollback_succeeds", [True, False])
def test_failed_final_alignment_rolls_back_mcp_host_manager_and_runtime(
    host_rollback_succeeds,
):
    with tempfile.TemporaryDirectory() as td:
        state_root = Path(td)
        candidate_tree = state_root / "candidate"
        create_candidate_scripts(candidate_tree)
        events = []
        align_calls = []

        def image_id(name):
            return {
                "jason-runtime:test-a": "sha256:runtime-a",
                "jason-mcp:test-a": "sha256:mcp-a",
            }.get(name, "sha256:unused")

        def run_command(args, *, cwd=None, env=None):
            command = str(args[0])
            rollback = str((env or {}).get("JASON_SOURCE_REVISION_OVERRIDE")) == SHA_B
            if "jason-runtime" in command:
                events.append("runtime-rollback" if rollback else "runtime")
            elif "jason-mcp" in command:
                events.append("mcp-rollback" if rollback else "mcp")
            return "DEPLOYMENT=PASS"

        def align(sha):
            align_calls.append(sha)
            if sha == SHA_A:
                raise runner.ReleaseManagerError("forced final alignment failure")
            return alignment(sha)

        def host(_state_root, sha, **_kwargs):
            events.append("host:" + sha)
            if sha == SHA_B and not host_rollback_succeeds:
                raise runner.ReleaseManagerError("SIMULATED_ROOT_HOST_RECONCILE_TIMEOUT")
            return {"success": True, "source_revision": sha}

        def manager(sha):
            events.append("manager:" + sha)
            return {
                "source_revision": sha,
                "timer_active": True,
                "source_link": f"/opt/jason/releases/{sha}",
            }

        with (
            patch.object(runner, "image_id", side_effect=image_id),
            patch.object(runner, "require_host_reconciler_ready"),
            patch.object(runner, "live_production_alignment", side_effect=align),
            patch.object(runner, "gate_transition", side_effect=fake_gate),
            patch.object(runner, "worktree", return_value=candidate_tree),
            patch.object(
                runner,
                "verify_candidate_host_reconciliation_contract",
                return_value={
                    "candidate_script_verified": True,
                    "managed_engineering_source_verified": True,
                    "managed_documentation_source_verified": True,
                    "developer_checkout_absent": True,
                },
            ),
            patch.object(
                runner,
                "verify_host_reconciliation_evidence",
                return_value={
                    "candidate_script_verified": True,
                    "managed_engineering_source_verified": True,
                    "managed_documentation_source_verified": True,
                    "developer_checkout_absent": True,
                },
            ),
            patch.object(runner, "remove_worktree"),
            patch.object(runner, "run", side_effect=run_command),
            patch.object(
                runner,
                "wait_live_runtime",
                side_effect=[
                    {"revision": SHA_A},
                    {"revision": SHA_B},
                ],
            ),
            patch.object(
                runner,
                "live_mcp",
                side_effect=[
                    {"revision": SHA_A},
                    {"revision": SHA_B},
                ],
            ),
            patch.object(runner, "request_host_reconcile", side_effect=host),
            patch.object(
                runner,
                "install_release_manager_from_current",
                side_effect=manager,
            ),
            patch.object(
                runner,
                "publish_production_closeout",
                return_value={"documentation": "pass", "control_board": "pass"},
            ),
            patch.object(runner, "rollback_surface_is_verified",
                         side_effect=[False, True, False, True]),
            patch.object(runner, "pin_exact_rollback_image"),
        ):
            release = record()
            with pytest.raises(
                runner.ReleaseManagerError,
                match="forced final alignment failure",
            ):
                runner.deploy_production(ROOT, state_root, release)

        assert release["state"] == ("rolled_back" if host_rollback_succeeds else "failed")
        assert release["failure"]["rollback_verified"] is host_rollback_succeeds
        assert release["failure"]["rollback_actions"]["host"] == (
            "reconciled_baseline" if host_rollback_succeeds else "unverified"
        )
        if host_rollback_succeeds:
            assert release["failure"]["rollback_errors"] == []
        else:
            assert any("SIMULATED_ROOT_HOST_RECONCILE_TIMEOUT" in item
                       for item in release["failure"]["rollback_errors"])
        assert events[:4] == [
            "runtime",
            "mcp",
            "host:" + SHA_A,
            "manager:" + SHA_A,
        ]
        assert "mcp-rollback" in events
        assert "host:" + SHA_B in events
        assert "manager:" + SHA_B in events
        assert "runtime-rollback" in events
        assert align_calls[0] == SHA_B
        assert SHA_A in align_calls
        # A failed root host rollback remains unverified: no final alignment
        # can be accepted as proof while its independent host step failed.
        assert align_calls[-1] == (SHA_B if host_rollback_succeeds else SHA_A)


def test_missing_root_host_reconciler_blocks_before_production_transition():
    with tempfile.TemporaryDirectory() as td:
        release = record()
        with (
            patch.object(
                runner,
                "image_id",
                side_effect=lambda name: {
                    "jason-runtime:test-a": "sha256:runtime-a",
                    "jason-mcp:test-a": "sha256:mcp-a",
                }[name],
            ),
            patch.object(
                runner,
                "require_host_reconciler_ready",
                side_effect=runner.ReleaseManagerError(
                    "root host reconciliation spool is not installed"
                ),
            ),
            patch.object(runner, "gate_transition") as gate,
            patch.object(runner, "run") as run_command,
        ):
            with pytest.raises(
                runner.ReleaseManagerError,
                match="root host reconciliation spool is not installed",
            ):
                runner.deploy_production(ROOT, Path(td), release)

        assert release["state"] == "production_eligible"
        gate.assert_not_called()
        run_command.assert_not_called()


def test_mcp_candidate_uses_established_governed_base_not_production():
    source = (ROOT / "tools" / "release_manager_host_runner.py").read_text(
        encoding="utf-8"
    )
    assert 'base = "jason-mcp:generic-governed-8f1e864947a2"' in source
    assert 'base = "jason-mcp:production"' not in source


@pytest.mark.parametrize("failed_stage", ["runtime", "mcp"])
@pytest.mark.parametrize("alias_repair", ["successful", "denied"])
def test_partially_mutated_deploy_script_failure_recovers_baseline(
    failed_stage, alias_repair, tmp_path
):
    """Simulate a script swapping containers and THEN returning nonzero.

    No Docker, systemd or production filesystem calls are permitted here.
    This failure can happen even though deploy_live_container.py attempts
    its own best-effort recovery, since its Docker restores use check=False.
    """
    candidate_tree = tmp_path / "candidate-source"
    create_candidate_scripts(candidate_tree)
    observed = {"runtime": SHA_B, "mcp": SHA_B, "host": SHA_B}
    events = []
    trip = {"failed": False}
    aliases = {
        # Before a forward image promotion, rollback-current still refers
        # to the PREVIOUS older release, not the current exact LKG.
        "jason-runtime:rollback-current": "sha256:" + "e" * 64,
        "jason-mcp:rollback-current": "sha256:" + "f" * 64,
    }

    def current_image(which):
        return {
            ("runtime", SHA_A): CANDIDATE_RUNTIME_IMAGE,
            ("runtime", SHA_B): BASELINE_RUNTIME_IMAGE,
            ("mcp", SHA_A): CANDIDATE_MCP_IMAGE,
            ("mcp", SHA_B): BASELINE_MCP_IMAGE,
        }[(which, observed[which])]

    def fake_image_id(tag):
        ids = {
            "jason-runtime:test-a": "sha256:runtime-a",
            "jason-mcp:test-a": "sha256:mcp-a",
            "jason-runtime:production": current_image("runtime"),
            "jason-mcp:production": current_image("mcp"),
        }
        return ids[tag] if tag in ids else aliases[tag]

    def fake_surface(which):
        return {"revision": observed[which], "image_id": current_image(which)}

    def fake_alignment(expected_sha):
        if any(rev != expected_sha for rev in observed.values()):
            raise runner.ReleaseManagerError(
                f"simulated mixed versions during alignment expected={expected_sha}"
            )
        return alignment(expected_sha)

    def fake_run(args, *, cwd=None, env=None):
        if args[0] == "docker":
            assert len(args) == 4 and args[1] == "tag"
            assert args[2] in {BASELINE_RUNTIME_IMAGE, BASELINE_MCP_IMAGE}
            assert args[3] in aliases
            events.append("pin:" + args[3])
            if alias_repair == "denied":
                raise runner.ReleaseManagerError("SIMULATED_IMMUTABLE_DOCKER_TAG_FAILURE")
            aliases[args[3]] = args[2]
            return ""
        name = str(args[0])
        which = "runtime" if "jason-runtime" in name else "mcp"
        sha = str((env or {}).get("JASON_SOURCE_REVISION_OVERRIDE"))
        if sha not in (SHA_A, SHA_B):
            raise AssertionError("unapproved source revision in simulated deploy")
        events.append(f"{which}:{'forward' if sha == SHA_A else 'rollback'}")
        observed[which] = sha
        if sha == SHA_A and which == failed_stage and not trip["failed"]:
            trip["failed"] = True
            raise runner.ReleaseManagerError(
                f"SIMULATED_PARTIAL_{which.upper()}_SWAP_SCRIPT_FAILED"
            )
        if sha == SHA_B:
            expected = (BASELINE_RUNTIME_IMAGE if which == "runtime"
                        else BASELINE_MCP_IMAGE)
            assert aliases[f"jason-{which}:rollback-current"] == expected
        return "DEPLOYMENT=PASS"

    with (
        patch.object(runner, "image_id", side_effect=fake_image_id),
        patch.object(runner, "require_host_reconciler_ready"),
        patch.object(runner, "live_production_alignment", side_effect=fake_alignment),
        patch.object(runner, "live_runtime", side_effect=lambda: fake_surface("runtime")),
        patch.object(runner, "live_mcp", side_effect=lambda: fake_surface("mcp")),
        patch.object(runner, "wait_live_runtime", side_effect=lambda: fake_surface("runtime")),
        patch.object(runner, "gate_transition", side_effect=fake_gate),
        patch.object(runner, "worktree", return_value=candidate_tree),
        patch.object(
            runner, "verify_candidate_host_reconciliation_contract",
            return_value={"root_source": True},
        ),
        patch.object(runner, "remove_worktree"),
        patch.object(runner, "run", side_effect=fake_run),
        patch.object(runner, "request_host_reconcile") as host_request,
        patch.object(runner, "install_release_manager_from_current") as manager_install,
        patch.object(runner, "open_circuit_breaker") as open_breaker,
    ):
        release = record()
        with pytest.raises(
            runner.ReleaseManagerError,
            match=f"SIMULATED_PARTIAL_{failed_stage.upper()}_SWAP_SCRIPT_FAILED",
        ):
            runner.deploy_production(ROOT, tmp_path, release)

    assert trip["failed"]
    assert f"pin:jason-{failed_stage}:rollback-current" in events
    open_breaker.assert_called_once()
    host_request.assert_not_called()
    manager_install.assert_not_called()
    if alias_repair == "successful":
        assert observed == {"runtime": SHA_B, "mcp": SHA_B, "host": SHA_B}
        assert events.count(f"{failed_stage}:rollback") == 1
        assert release["state"] == "rolled_back"
        assert release["failure"]["rollback_verified"] is True
        assert release["failure"]["rollback_errors"] == []
        assert release["failure"]["rollback_actions"][failed_stage] == "restored_and_verified"
        assert open_breaker.call_args.kwargs["rollback_verified"] is True
    else:
        # Refuse to reuse a stale image tag or claim an unverified rollback.
        assert events.count(f"{failed_stage}:rollback") == 0
        assert observed[failed_stage] == SHA_A
        assert release["state"] == "failed"
        assert release["failure"]["rollback_verified"] is False
        assert release["failure"]["rollback_actions"][failed_stage] == "unverified"
        assert any("SIMULATED_IMMUTABLE_DOCKER_TAG_FAILURE" in err
                   for err in release["failure"]["rollback_errors"])
        assert open_breaker.call_args.kwargs["rollback_verified"] is False


def test_preflight_script_failure_at_unchanged_baseline_does_not_restart_runtime(tmp_path):
    """A failure before a swap must not unnecessarily disrupt healthy users."""
    candidate_tree = tmp_path / "candidate-source"
    create_candidate_scripts(candidate_tree)
    events = []

    def fake_image_id(tag):
        return {
            "jason-runtime:test-a": "sha256:runtime-a",
            "jason-mcp:test-a": "sha256:mcp-a",
            "jason-runtime:production": BASELINE_RUNTIME_IMAGE,
            "jason-mcp:production": BASELINE_MCP_IMAGE,
        }[tag]

    def fake_run(args, *, cwd=None, env=None):
        assert "jason-runtime" in str(args[0])
        events.append("runtime-call")
        raise runner.ReleaseManagerError("SIMULATED_FAILED_PRIOR_TO_ANY_MUTATION")

    with (
        patch.object(runner, "image_id", side_effect=fake_image_id),
        patch.object(runner, "require_host_reconciler_ready"),
        patch.object(runner, "live_production_alignment", side_effect=alignment),
        patch.object(runner, "live_runtime",
                     return_value={"revision": SHA_B, "image_id": BASELINE_RUNTIME_IMAGE}),
        patch.object(runner, "live_mcp",
                     return_value={"revision": SHA_B, "image_id": BASELINE_MCP_IMAGE}),
        patch.object(runner, "gate_transition", side_effect=fake_gate),
        patch.object(runner, "worktree", return_value=candidate_tree),
        patch.object(runner, "verify_candidate_host_reconciliation_contract",
                     return_value={"root_source": True}),
        patch.object(runner, "remove_worktree"),
        patch.object(runner, "run", side_effect=fake_run),
        patch.object(runner, "request_host_reconcile") as host_request,
        patch.object(runner, "install_release_manager_from_current") as manager_install,
        patch.object(runner, "open_circuit_breaker") as open_breaker,
    ):
        release = record()
        with pytest.raises(runner.ReleaseManagerError,
                           match="SIMULATED_FAILED_PRIOR_TO_ANY_MUTATION"):
            runner.deploy_production(ROOT, tmp_path, release)

    assert events == ["runtime-call"], "do not reboot an unchanged healthy runtime"
    assert release["state"] == "rolled_back"
    assert release["failure"]["rollback_verified"] is True
    assert release["failure"]["rollback_actions"]["runtime"] == "already_verified_at_baseline"
    assert release["failure"]["rollback_actions"]["mcp"] == "not_attempted"
    host_request.assert_not_called()
    manager_install.assert_not_called()
    open_breaker.assert_called_once()

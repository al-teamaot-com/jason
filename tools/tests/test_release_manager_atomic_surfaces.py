import importlib.util
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

SHA_A = "a" * 40
SHA_B = "b" * 40


def record():
    return {
        "schema_version": "2.0",
        "release_id": runner.record_id(SHA_A),
        "state": "production_eligible",
        "rollback_sha": SHA_B,
        "release_candidate": {
            "candidate_sha": SHA_A,
            "image": "jason-runtime:test-a",
            "artifact_digest": "sha256:runtime-a",
            "mcp_image": "jason-mcp:test-a",
            "mcp_artifact_digest": "sha256:mcp-a",
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


def fake_gate(_repo, release, target):
    release["state"] = target
    release.setdefault("history", []).append(
        {"state": target, "gate": "pass"}
    )


def test_atomic_deploy_updates_runtime_mcp_host_and_release_manager_before_close():
    with tempfile.TemporaryDirectory() as td:
        state_root = Path(td)
        candidate_tree = state_root / "candidate"
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
        ):
            result = runner.deploy_production(ROOT, state_root, record())

        assert result["state"] == "closed"
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


def test_failed_final_alignment_rolls_back_mcp_host_manager_and_runtime():
    with tempfile.TemporaryDirectory() as td:
        state_root = Path(td)
        candidate_tree = state_root / "candidate"
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
        ):
            release = record()
            with pytest.raises(
                runner.ReleaseManagerError,
                match="forced final alignment failure",
            ):
                runner.deploy_production(ROOT, state_root, release)

        assert release["state"] == "rolled_back"
        assert release["failure"]["rollback_verified"] is True
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
        assert align_calls[-1] == SHA_B


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

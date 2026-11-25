"""Fixed documentation actions for the governed objective executor.

No caller supplies a command, unit name, path or publisher bytes. The installed
bootstrap seals the exact manifest after independently checking native state.
The original failed approval is retained; a NEW original Teams objective is the
authority for this repair, never a replay of its expired installation decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from typing import Mapping

from tools.pmv4_teams_objective_admission import canonical, need

PUBLISHER_SOURCE = "49d386bf9472c5b2adc78499fe5d6041e6167ebe"
PUBLISHER_BASE = Path("/usr/local/lib/jason/documentation-reconciliation")
DROPIN = Path("/etc/systemd/system/jason-documentation-reconciliation.service.d/20-reviewed-publisher.conf")
UNIT = "jason-documentation-reconciliation.service"
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
WORKTREE = Path("/home/al/jason-worktrees/documentation-reconcile-current")
PAYLOAD = {
    "tools/documentation_source_reconciler.py": "7eacdf6e368c13da13807ebba513acc6481f97f2bce852bff09423960b56f5fc",
    "tools/publish_documentation_reconciliation.sh": "1c5ff7a73835cd55710cf01c16f2efc39e44986618ed88d44d6f66e35b9a46dd",
}
RESTORE = "release.documentation.publisher.restore"
VERIFY = "release.documentation.publisher.verify"


def override_bytes() -> bytes:
    return ("[Service]\nExecStart=\nExecStart=/usr/bin/python3 -B "
            + str(PUBLISHER_BASE / PUBLISHER_SOURCE / "tools/documentation_source_reconciler.py")
            + "\n").encode()


class DocumentationObjectiveActions:
    def __init__(self, *, manifest: dict, native: dict, verify_source,
                 receipt_directory: Path, production: bool = True):
        if production:
            need(os.geteuid() == 0
                 and Path(__file__).resolve() == Path(
                     "/usr/local/lib/jason/owner-objective/trusted/tools/pmv4_objective_documentation.py"),
                 "INSTALLED_DOCUMENTATION_ACTION_REQUIRED")
        self.manifest, self.native, self.verify_source = manifest, native, verify_source
        self.receipts, self.production = receipt_directory, production
        self.native["directory"](self.receipts, 0 if production else os.geteuid(), 0o700)

    def preflight(self, *, after_restore: bool = False) -> bool:
        c, m = self.native, self.manifest
        for path, uid, mode, field in (
            (Path("/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json"),
             1000, 0o600, "engineering_pause_sha256"),
            (Path("/usr/local/lib/jason/release_host_reconcile_worker.py"),
             0, 0o755, "shared_worker_sha256"),
        ):
            need(sha256(c["read"](path, uid, mode)).hexdigest() == m[field],
                 "PROTECTED_EXECUTOR_OR_OWNER_PAUSE_CHANGED")
        hashes = m["accepted_native_files_sha256"]
        need(isinstance(hashes, dict) and len(hashes) == 64, "ACCEPTED_NATIVE_CLOSURE_REQUIRED")
        c["directory"](c["NATIVE"], 0, 0o555)
        for name, expected in hashes.items():
            need(sha256(c["read"](c["NATIVE"] / name, 0, 0o444)).hexdigest() == expected,
                 "ACCEPTED_STAGE_E_CODE_CHANGED")
        need(self.verify_source(m["candidate_sha"]) is True, "PROTECTED_SOURCE_OR_CI")
        need(c["peers"]() == m["protected_peers"], "PROTECTED_PEER_CHANGED")
        for path, uid, mode, expected in (
            (Path(m["freeze_path"]), 1000, 0o600, m["freeze_sha256"]),
            (Path(m["hold_path"]), 1000, 0o664, m["hold_sha256"]),
            (Path(m["root_policy_path"]), 0, 0o600, m["root_policy_sha256"]),
            (Path(m["stage_e_marker_path"]), 0, 0o444, m["stage_e_marker_sha256"]),
            (Path("/etc/systemd/system") / UNIT, 0, 0o644, m["original_unit_sha256"]),
        ):
            need(sha256(c["read"](path, uid, mode)).hexdigest() == expected,
                 "DOCUMENTATION_PROTECTION_DRIFT")
        for name, expected in PAYLOAD.items():
            need(sha256(c["read"](PUBLISHER_BASE / PUBLISHER_SOURCE / name, 0, 0o444)).hexdigest()
                 == expected, "ORIGINAL_PUBLISHER_PAYLOAD_CHANGED")
        control = json.loads(c["read"](MANAGER / "production-control-state.json", 0, 0o600))
        drift = json.loads(c["read"](MANAGER / "production-drift.json", 0, 0o600))
        need(control["circuit_breaker"]["state"] == "closed"
             and drift["status"] == "pass" and drift["problems"] == [], "PRODUCTION_GATE")
        at = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
        need(0 <= (datetime.now(timezone.utc) - at).total_seconds() <= 180, "DRIFT_STALE")
        repo = Path("/home/al/.local/lib/jason/documentation-source-repo")
        common = ("rev-parse", "--path-format=absolute", "--git-common-dir")
        need(c["git"](repo, *common) == c["git"](WORKTREE, *common),
             "DOCUMENTATION_WORKTREE_OWNER")
        need(c["git"](repo, "status", "--porcelain", "--untracked-files=all") == ""
             and c["git"](WORKTREE, "status", "--porcelain", "--untracked-files=all") == "",
             "DOCUMENTATION_WORKTREE_DIRTY")
        state = c["props"](UNIT, False)
        need(state["ActiveState"] in ("inactive", "failed"), "DOCUMENTATION_SERVICE_BUSY")
        if after_restore:
            need(c["read"](DROPIN, 0, 0o644) == override_bytes()
                 and str(PUBLISHER_BASE / PUBLISHER_SOURCE) in state["ExecStart"]
                 and state.get("DropInPaths", "").split() == [str(DROPIN)],
                 "REVIEWED_DOCUMENTATION_SOURCE_NOT_ACTIVE")
        elif os.path.lexists(DROPIN):
            need(c["read"](DROPIN, 0, 0o644) == override_bytes()
                 and str(PUBLISHER_BASE / PUBLISHER_SOURCE) in state["ExecStart"]
                 and state.get("DropInPaths", "").split() == [str(DROPIN)],
                 "FOREIGN_DOCUMENTATION_OVERRIDE")
        else:
            need(state.get("DropInPaths", "") == "", "FOREIGN_DOCUMENTATION_OVERRIDE")
        return True

    def _host(self):
        if not self.production:
            return nullcontext()
        need(callable(self.native.get("objective_host_transaction")), "SHARED_HOST_TRANSACTION_REQUIRED")
        return self.native["objective_host_transaction"]()

    def _record(self, claim: dict, *, status: str) -> dict:
        args = claim["step_material"]["arguments"]
        return dict(status=status, approval_id=claim["approval_id"],
            plan_fingerprint=claim["plan_fingerprint"], step_index=claim["step_index"],
            claim_id=claim["claim_id"], candidate_sha=args["candidate_sha"],
            scope_sha256=args["scope_sha256"], manifest_sha256=args["manifest_sha256"])

    def execute(self, claim: dict) -> dict:
        step, c = claim["step_material"], self.native
        need(step["arguments"] == self.manifest["step_arguments"], "DOCUMENTATION_MANIFEST_SCOPE")
        receipt = self.receipts / (claim["claim_id"] + ".json")
        if receipt.exists():
            return self.readback(claim)
        if step["capability_name"] == RESTORE:
            with self._host():
                self.preflight()
                created_parent = not DROPIN.parent.exists()
                if created_parent:
                    DROPIN.parent.mkdir(mode=0o755)
                c["directory"](DROPIN.parent, 0)
                created = False
                try:
                    if not os.path.lexists(DROPIN):
                        c["write"](DROPIN, override_bytes(), 0o644)
                        created = True
                        c["systemctl"](["daemon-reload"])
                    self.preflight(after_restore=True)
                    result = self._record(claim, status="verified")
                    c["write"](receipt, canonical(result), 0o400)
                    return result
                except BaseException:
                    if created:
                        need(c["read"](DROPIN, 0, 0o644) == override_bytes(), "FOREIGN_OVERRIDE_ON_ROLLBACK")
                        DROPIN.unlink()
                        if created_parent and not any(DROPIN.parent.iterdir()):
                            DROPIN.parent.rmdir()
                        c["systemctl"](["daemon-reload"])
                    raise
        need(step["capability_name"] == VERIFY, "UNREGISTERED_ROOT_ACTION")
        with self._host():
            self.preflight(after_restore=True)
            phase = self.receipts / (claim["claim_id"] + ".started.json")
            # Seal the before-image before starting the one bounded native job.
            # A crash never authorizes a second start under this claim.
            need(not os.path.lexists(phase), "NATIVE_JOB_ALREADY_CLAIMED")
            before = self._job_state()
            c["write"](phase, canonical({
                "claim_id": claim["claim_id"],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "before_invocation_id": before.get("InvocationID", ""),
                "monotonic_us": time.monotonic_ns() // 1000,
            }), 0o400)
            c["systemctl"](["reset-failed", UNIT])
            c["systemctl"](["start", "--no-block", UNIT])
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = c["props"](UNIT, False)
            if state["ActiveState"] not in ("active", "activating", "deactivating"):
                break
            time.sleep(2)
        return self._finish_verified_job(claim)

    def _job_state(self):
        raw = self.native["run"](["/usr/bin/systemctl", "show", UNIT,
            "--property=Result,ExecMainStatus,InvocationID,ExecMainStartTimestampMonotonic"])
        return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)

    def _finish_verified_job(self, claim):
        c = self.native
        phase = json.loads(c["read"](self.receipts / (claim["claim_id"] + ".started.json"), 0, 0o400))
        state, result = c["props"](UNIT, False), self._job_state()
        need(phase["claim_id"] == claim["claim_id"]
             and phase["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
             and state["ActiveState"] == "inactive"
             and result.get("Result") == "success" and result.get("ExecMainStatus") == "0"
             and result.get("InvocationID") not in ("", phase["before_invocation_id"])
             and int(result.get("ExecMainStartTimestampMonotonic", "0")) >= phase["monotonic_us"],
             "DOCUMENTATION_SCHEDULED_JOB_NOT_VERIFIED")
        generated = json.loads((WORKTREE / "docs/control/AUTOMATED-CHANGE-STATE.json").read_bytes())
        need(generated["validated_source"]["revision"] == self.manifest["candidate_sha"],
             "DOCUMENTATION_GENERATED_SOURCE_NOT_CURRENT")
        c["systemctl"](["start", "jason-production-drift-watchdog.service"])
        with self._host():
            self.preflight(after_restore=True)
            result = self._record(claim, status="verified")
            accepted = PUBLISHER_BASE / "accepted.json"
            if os.path.lexists(accepted):
                self._prior_acceptance()
            else:
                c["write"](accepted, canonical({
                    **result, "status": "documentation_publisher_operationally_verified",
                    "source_sha": PUBLISHER_SOURCE,
                    "authorization": "original_signed_teams_owner_objective",
                    "protected_services_changed": False, "provider_mutations": False,
                    "github_documentation_publication": True,
                    "accepted_at": datetime.now(timezone.utc).isoformat(),
                }), 0o400)
            c["write"](self.receipts / (claim["claim_id"] + ".json"), canonical(result), 0o400)
            return result

    def _prior_acceptance(self):
        accepted = json.loads(self.native["read"](PUBLISHER_BASE / "accepted.json", 0, 0o400))
        need(accepted.get("status") == "documentation_publisher_operationally_verified"
             and accepted.get("authorization") == "original_signed_teams_owner_objective"
             and accepted.get("source_sha") == PUBLISHER_SOURCE,
             "FOREIGN_DOCUMENTATION_ACCEPTANCE")
        return accepted

    def readback(self, claim: dict) -> Mapping:
        """Recover verified native facts, never rerun an uncertain service job."""
        receipt = self.receipts / (claim["claim_id"] + ".json")
        if receipt.exists():
            result = json.loads(self.native["read"](receipt, 0, 0o400))
            need(result == self._record(claim, status="verified"), "NATIVE_DOCUMENTATION_RECEIPT")
            self.preflight(after_restore=True)
            return result
        # After a crash following final acceptance, the Root-owned accepted
        # record can recover this exact completed step without another vote/job.
        if claim["step_material"]["capability_name"] == VERIFY:
            if not os.path.lexists(PUBLISHER_BASE / "accepted.json"):
                # Read the fresh native invocation sealed before the start.
                # This also covers a crash after the job finished but before
                # the small acceptance receipt was committed.
                return self._finish_verified_job(claim)
            accepted = self._prior_acceptance()
            expected = self._record(claim, status="verified")
            if not all(accepted.get(k) == v for k, v in expected.items() if k != "status"):
                # An older objective's acceptance cannot prove this new job.
                # Recover only this claim's independently sealed fresh invocation.
                return self._finish_verified_job(claim)
            self.preflight(after_restore=True)
            self.native["write"](receipt, canonical(expected), 0o400)
            return expected
        if claim["step_material"]["capability_name"] == RESTORE:
            # The exact desired Root configuration itself is independent
            # readback evidence after a crash before its small receipt.
            self.preflight(after_restore=True)
            expected = self._record(claim, status="verified")
            self.native["write"](receipt, canonical(expected), 0o400)
            return expected
        raise PermissionError("DOCUMENTATION_NATIVE_CLAIM_NEEDS_INDEPENDENT_READBACK")

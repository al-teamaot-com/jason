"""Protected enrollment and one-use native claims for the existing plan service.

The canonical human decision stays in the existing ApprovalRequestService.
This store retains Root's independently verified original evidence and native
claim/readback facts. It never votes, signs an Owner credential or runs commands.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
from typing import Any, Callable, Mapping

from tools.pmv4_teams_objective_admission import (
    TeamsObjectiveDenied, canonical, need, plan_digest, timestamp, validate_enrollment,
    verify_original_teams_decision,
)

def _atomic_json(path, record):
    """Publish a private immutable receipt under the Root plan lock.

    Staging owns a newly created private directory. Every subsequent writer
    holds its plan lock; operator-writable ancestors are never used here.
    """
    if os.path.lexists(path):
        raise FileExistsError("immutable Root receipt already exists")
    fd, temporary = tempfile.mkstemp(prefix=".objective-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(canonical(record)); stream.flush(); os.fsync(stream.fileno())
        os.rename(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


ROOT = Path("/var/lib/jason-owner-release/objectives")
ENTRY = Path("/usr/local/lib/jason/owner-objective/trusted/tools/pmv4_teams_objective_store.py")
_ID = re.compile(r"planapproval-(?:objective-)?[0-9a-f]{32}\Z")


class RootObjectiveStore:
    def __init__(self, *, root: Path = ROOT, production: bool = True):
        if production:
            need(os.geteuid() == 0 and root == ROOT and Path(__file__).resolve() == ENTRY,
                 "INSTALLED_ROOT_STORE_REQUIRED")
        else:
            need(root.is_absolute() and Path("/tmp") in root.resolve().parents,
                 "DISPOSABLE_STORE_REQUIRED")
        self.root, self.production = root, production
        self._directory(root)

    def _directory(self, path: Path) -> None:
        m = path.lstat()
        need(not path.is_symlink() and path.resolve() == path and stat.S_ISDIR(m.st_mode)
             and m.st_uid == os.geteuid() and stat.S_IMODE(m.st_mode) == 0o700,
             "ROOT_DIRECTORY_IDENTITY")

    def _plan(self, approval_id: str) -> Path:
        need(type(approval_id) is str and _ID.fullmatch(approval_id) is not None,
             "ROOT_PLAN_ID")
        path = self.root / approval_id
        self._directory(path)
        return path

    def _read(self, path: Path) -> dict:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            m = os.fstat(stream.fileno())
            link = path.lstat()
            need(stat.S_ISREG(m.st_mode) and not stat.S_ISLNK(link.st_mode)
                 and (m.st_dev, m.st_ino) == (link.st_dev, link.st_ino)
                 and m.st_uid == os.geteuid() and m.st_nlink == 1
                 and stat.S_IMODE(m.st_mode) == 0o600 and 0 < m.st_size <= 196608,
                 "ROOT_FILE_IDENTITY")
            raw = stream.read(196609)
        need(len(raw) == m.st_size, "ROOT_FILE_CHANGED")
        data = json.loads(raw)
        need(isinstance(data, dict), "ROOT_FILE_SCHEMA")
        return data

    @contextmanager
    def _locked(self, path: Path):
        fd = os.open(path / "root-plan.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            m = os.fstat(fd)
            need(stat.S_ISREG(m.st_mode) and m.st_nlink == 1
                 and m.st_uid == os.geteuid() and stat.S_IMODE(m.st_mode) == 0o600,
                 "ROOT_LOCK_IDENTITY")
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def stage(self, *, approval_id: str, material: dict, at: datetime,
              policy_digest: str, allowed_components: frozenset[str],
              allowed_requesters: frozenset[str], native_preflight: Callable[[dict], bool]) -> dict:
        """Preflight and retain exact candidate facts BEFORE presenting a card."""
        need(type(approval_id) is str and _ID.fullmatch(approval_id) is not None,
             "ROOT_PLAN_ID")
        candidate = dict(
            schema_version="1.0", approval_id=approval_id,
            plan_fingerprint=plan_digest(material), material=material,
            card_instance_challenge=secrets.token_hex(24), provider_message_id=None,
            staged_at=at.isoformat())
        scope, steps = validate_enrollment(candidate, policy_digest=policy_digest,
            allowed_components=allowed_components, delivery_required=False)
        need(all(s["principal_id"] in allowed_requesters for s in steps),
             "REQUESTER_NOT_REGISTERED")
        need(timestamp(candidate["staged_at"]) < timestamp(scope["expires_at"]),
             "STAGING_EXPIRED")
        # Installed code supplies this port. It must read the real immutable
        # component bundles, protected CI/health, baseline and rollback itself.
        need(callable(native_preflight) and native_preflight(candidate) is True,
             "NATIVE_PREFLIGHT")
        path = self.root / approval_id
        if path.exists() or path.is_symlink():
            self._directory(path)
            prior = self._read(path / "enrollment.json")
            need(prior["material"] == material and prior["plan_fingerprint"] == candidate["plan_fingerprint"],
                 "STAGED_PLAN_CHANGED")
            return prior
        path.mkdir(mode=0o700)
        _atomic_json(path / "enrollment.json", candidate)
        return candidate

    def record_delivery(self, *, approval_id: str, provider_message_id: str,
                        policy_digest: str, allowed_components: frozenset[str]) -> None:
        path = self._plan(approval_id)
        with self._locked(path):
            enrollment = self._read(path / "enrollment.json")
            enrollment["provider_message_id"] = provider_message_id
            validate_enrollment(enrollment, policy_digest=policy_digest,
                                allowed_components=allowed_components)
            delivery = path / "delivery.json"
            facts = {"provider_message_id": provider_message_id,
                     "plan_fingerprint": enrollment["plan_fingerprint"]}
            if delivery.exists():
                need(self._read(delivery) == facts, "DELIVERY_CHANGED_OR_REPLAYED")
                return
            _atomic_json(delivery, facts)

    def deliver(self, *, approval_id, at, policy_digest, allowed_components, native_delivery):
        """Root sends its own exact review. A caller cannot attest a delivery."""
        path = self._plan(approval_id)
        with self._locked(path):
            enrollment = self._read(path / "enrollment.json")
            validate_enrollment(enrollment, policy_digest=policy_digest,
                allowed_components=allowed_components, delivery_required=False)
            need(at < timestamp(enrollment["material"]["scope"]["expires_at"]), "DELIVERY_PLAN_EXPIRED")
            delivery = path / "delivery.json"
            if delivery.exists():
                return self._read(delivery)["provider_message_id"]
            claim = path / "delivery-claim.json"
            need(not os.path.lexists(claim), "CARD_SEND_OUTCOME_UNKNOWN_NO_RESEND")
            _atomic_json(claim, {"plan_fingerprint": enrollment["plan_fingerprint"],
                                  "claimed_at": at.isoformat()})
            message = native_delivery(enrollment)
            bound = dict(enrollment, provider_message_id=message)
            validate_enrollment(bound, policy_digest=policy_digest,
                                allowed_components=allowed_components)
            _atomic_json(delivery, {"provider_message_id": message,
                                   "plan_fingerprint": enrollment["plan_fingerprint"]})
            return message

    def _enrollment(self, path: Path) -> dict:
        enrollment = self._read(path / "enrollment.json")
        delivered = self._read(path / "delivery.json")
        need(delivered["plan_fingerprint"] == enrollment["plan_fingerprint"], "DELIVERY_SCOPE")
        enrollment["provider_message_id"] = delivered["provider_message_id"]
        return enrollment

    def _decision(self, path: Path, *, signed_envelope: Mapping[str, Any], at: datetime,
                  verify_ports: dict):
        need(not os.path.lexists(path / "revoked.json"), "ROOT_PLAN_REVOKED")
        original = path / "verified-decision.json"
        retained = self._read(original) if original.exists() else None
        if retained is not None:
            need(retained["signed_envelope"] == signed_envelope, "ORIGINAL_DECISION_CHANGED")
        verified = verify_original_teams_decision(
            enrollment=self._enrollment(path), signed_envelope=signed_envelope, at=at,
            previously_verified_at=(timestamp(retained["verified_at"]) if retained else None),
            **verify_ports)
        if retained is None:
            _atomic_json(original, {
                "signed_envelope": dict(signed_envelope), "verified_at": at.isoformat(),
                "evidence_sha256": verified.evidence_sha256,
                "plan_fingerprint": verified.plan_fingerprint,
            })
        else:
            need(retained["evidence_sha256"] == verified.evidence_sha256
                 and retained["plan_fingerprint"] == verified.plan_fingerprint,
                 "RETAINED_DECISION_CHANGED")
        return verified

    def admit(self, *, approval_id, signed_envelope, at, verify_ports):
        """Retain the real human decision while its transport is fresh.

        Native release gates remain independent. Their temporary failure must
        not discard an already verified Owner decision or demand another vote.
        """
        path = self._plan(approval_id)
        with self._locked(path):
            verified = self._decision(path, signed_envelope=signed_envelope, at=at,
                                      verify_ports=verify_ports)
            return {"approval_id": approval_id, "plan_fingerprint": verified.plan_fingerprint,
                    "owner_decision_recorded": True}

    def claim(self, *, approval_id: str, step_index: int, signed_envelope: Mapping[str, Any],
              at: datetime, verify_ports: dict, native_preflight: Callable[[dict, dict], bool],
              readback_only: bool = False) -> dict:
        path = self._plan(approval_id)
        with self._locked(path):
            enrollment = self._enrollment(path)
            steps = enrollment["material"]["requests"]
            need(type(step_index) is int and 0 <= step_index < len(steps), "STEP_INDEX")
            # No claim or verified-decision record is written if native gates fail.
            need(callable(native_preflight) and native_preflight(enrollment, steps[step_index]) is True,
                 "NATIVE_PREFLIGHT")
            decision = self._decision(path, signed_envelope=signed_envelope,
                                      at=at, verify_ports=verify_ports)
            for prior in range(step_index):
                claimed = self._read(path / ("claim-" + str(prior) + ".json"))
                outcome = self._read(path / ("outcome-" + str(prior) + ".json"))
                need(outcome["status"] == "verified" and outcome["claim_id"] == claimed["claim_id"]
                     and outcome["plan_fingerprint"] == decision.plan_fingerprint
                     and outcome["step_index"] == prior, "PRIOR_NATIVE_STEP_NOT_VERIFIED")
            step = steps[step_index]
            claim_id = decision.claim_id(step_index, step)
            claim = dict(approval_id=approval_id, plan_fingerprint=decision.plan_fingerprint,
                         step_index=step_index, claim_id=claim_id,
                         step_material=step, owner_evidence_sha256=decision.evidence_sha256)
            target = path / ("claim-" + str(step_index) + ".json")
            if target.exists():
                need(self._read(target) == claim, "CLAIM_CHANGED")
                outcome = path / ("outcome-" + str(step_index) + ".json")
                need(outcome.exists() or readback_only,
                     "INDETERMINATE_NATIVE_CLAIM_REQUIRES_READBACK")
                return dict(claim, already_verified=outcome.exists(), readback_only=True)
            need(not readback_only, "NO_EXISTING_NATIVE_CLAIM_TO_READBACK")
            _atomic_json(target, claim)
            return dict(claim, already_verified=False)

    def complete_from_native_readback(
        self, *, approval_id: str, step_index: int,
        native_readback: Callable[[dict], Mapping[str, Any]],
    ) -> dict:
        """An installed native reader owns the outcome; request JSON cannot supply it."""
        path = self._plan(approval_id)
        with self._locked(path):
            claim = self._read(path / ("claim-" + str(step_index) + ".json"))
            outcome = dict(native_readback(claim))
            args = claim["step_material"]["arguments"]
            need(outcome.get("status") == "verified"
                 and outcome.get("approval_id") == approval_id
                 and outcome.get("plan_fingerprint") == claim["plan_fingerprint"]
                 and outcome.get("step_index") == step_index
                 and outcome.get("claim_id") == claim["claim_id"]
                 and outcome.get("candidate_sha") == args["candidate_sha"]
                 and outcome.get("scope_sha256") == args["scope_sha256"]
                 and outcome.get("manifest_sha256") == args["manifest_sha256"],
                 "NATIVE_OUTCOME_NOT_VERIFIED")
            target = path / ("outcome-" + str(step_index) + ".json")
            if target.exists():
                need(self._read(target) == outcome, "NATIVE_OUTCOME_CHANGED")
            else:
                _atomic_json(target, outcome)
            return outcome

    def status(self, *, approval_id: str) -> dict:
        path = self._plan(approval_id)
        with self._locked(path):
            enrollment = self._read(path / "enrollment.json")
            completed = 0
            for index in range(len(enrollment["material"]["requests"])):
                if not (path / ("outcome-" + str(index) + ".json")).exists():
                    break
                outcome = self._read(path / ("outcome-" + str(index) + ".json"))
                claim = self._read(path / ("claim-" + str(index) + ".json"))
                need(outcome["status"] == "verified" and outcome["claim_id"] == claim["claim_id"],
                     "NATIVE_STATUS_CHANGED")
                completed += 1
            count = len(enrollment["material"]["requests"])
            indeterminate = (path / ("claim-" + str(completed) + ".json")).exists()
            return dict(approval_id=approval_id, plan_fingerprint=enrollment["plan_fingerprint"],
                completed_steps=completed, total_steps=count,
                state=("revoked" if (path / "revoked.json").exists() else
                       "verified_complete" if completed == count else
                       "indeterminate" if indeterminate else "awaiting_step"))

    def revoke_from_root(self, *, approval_id: str, verified_revocation_sha256: str) -> None:
        """Only the installed authenticated revocation handler may invoke this."""
        need(type(verified_revocation_sha256) is str
             and re.fullmatch(r"[0-9a-f]{64}", verified_revocation_sha256) is not None,
             "REVOCATION_EVIDENCE")
        path = self._plan(approval_id)
        with self._locked(path):
            _atomic_json(path / "revoked.json", {
                "approval_id": approval_id,
                "verified_revocation_sha256": verified_revocation_sha256,
            })

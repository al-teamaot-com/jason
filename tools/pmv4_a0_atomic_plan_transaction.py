"""Crash-durable three-step A0 transaction coordinator — SOURCE-ONLY.

Engineering admission of one signed *whole* Owner decision for exactly
bootstrap -> immutable one-file root closure -> native Stage A0. Only disposable
private /tmp tests may invoke this coordinator. It DOES NOT install into
production; production raises before file creation, owner grant, or root work.

The future root controller must use native fixed-function adapters under ONE
root-held legacy release lease and pin this source+policy as trusted code.
A generic callback or operator-owned SQLite is NOT valid root authority.
"""
from __future__ import annotations

from datetime import datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping, Protocol, Sequence

from kernel.signed_owner_release import canonical
from tools.pmv4_stage_a0_one_owner_review import (
    build_reviewed_plan, REVIEWED_ACTIONS, CONTRACT_SHA256, SOURCE,
)
from tools.pmv4_bounded_plan_journal import BoundedPlanJournal
from tools.pmv4_current_grant_attestation import (
    verify_current_grant_attestation,
)
from orchestrator.pmv4_objective_scope import BoundedObjective


class A0AtomicTransactionDenied(PermissionError):
    pass


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


class A0StageSandboxAdapter(Protocol):
    def apply(self, index: int, evidence: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def verify_installed(self, index: int) -> bool: ...
    def rollback_exact(self, index: int) -> Mapping[str, Any]: ...
    def verify_absent(self, index: int) -> bool: ...


class A0AtomicSandboxTransaction:
    """Three-effect all-or-rollback sandbox acceptance.

    The root-owned native variant is NOT DEPLOYED. This test coordinator uses
    a fixed three-action allowlist, one signed parent/approval, current signed
    authorization per action, and a durable one-use exclusive claim ledger.
    Never accept caller-supplied prior-step completion lists.
    """

    def __init__(
        self, *, directory: Path, objective: BoundedObjective,
        signed_parent: Mapping[str, Any], pinned_public_key: Any,
        bounded_journal: BoundedPlanJournal,
        production: bool = False,
    ) -> None:
        if production:
            raise A0AtomicTransactionDenied("A0_ATOMIC_PRODUCTION_ROOT_CONSUMER_NOT_DEPLOYED")
        if (not isinstance(directory, Path) or not directory.is_absolute()
                or directory.is_symlink() or not directory.is_dir()
                or not directory.resolve(strict=True) == directory
                or Path("/tmp") not in directory.parents
                or not isinstance(objective, BoundedObjective)
                or not isinstance(signed_parent, Mapping)
                or not isinstance(bounded_journal, BoundedPlanJournal)):
            raise A0AtomicTransactionDenied("A0_ATOMIC_DISPOSABLE_SANDBOX_REQUIRED")
        dstat = directory.lstat()
        if (dstat.st_uid != os.geteuid()
                or not stat.S_ISDIR(dstat.st_mode)
                or stat.S_IMODE(dstat.st_mode) != 0o700
                or len(objective.actions) != 3
                or objective.candidate_sha != SOURCE
                or objective.policy_digest != CONTRACT_SHA256
                or [(a.capability, a.component, a.scope_sha256,
                     a.artifact_sha256) for a in objective.actions]
                   != list(REVIEWED_ACTIONS)
                or bounded_journal.objective != objective
                or bounded_journal.signed_parent != dict(signed_parent)
                or signed_parent.get("payload", {}).get("reviewed_objective")
                   != objective.review_material()):
            raise A0AtomicTransactionDenied("A0_ATOMIC_PINNED_THREE_STAGE_SCOPE_REQUIRED")
        self.directory = directory
        self.objective = objective
        self.signed_parent = dict(signed_parent)
        self.bounded = bounded_journal
        self.pinned_public_key = pinned_public_key
        self.parent_hash = _digest(canonical(self.signed_parent))
        self.path = directory / "pmv4-stage-a0-atomic-release.jsonl"
        self.lock_path = directory / "pmv4-stage-a0-atomic-release.lock"

    def _open_lock(self) -> int:
        fd = os.open(self.lock_path,
                     os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            os.close(fd)
            raise A0AtomicTransactionDenied("A0_ATOMIC_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            os.close(fd)
            raise A0AtomicTransactionDenied("A0_ATOMIC_RELEASE_ALREADY_RUNNING") from exc
        return fd

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_SYMLINK")
        fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 128 * 1024):
                raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_UNTRUSTED")
            raw = os.read(fd, 128 * 1024 + 1)
        finally:
            os.close(fd)
        if not raw.endswith(b"\n"):
            raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_TORN")
        rows = []
        prev = "0" * 64
        for line in raw.splitlines():
            try:
                x = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_INVALID_JSON") from exc
            if (not isinstance(x, dict)
                    or set(x) != {"version", "seq", "action", "step",
                                   "parent_sha256", "review_sha256", "detail_sha256",
                                   "prev_sha256", "hash"}
                    or x["version"] != 1
                    or type(x["seq"]) is not int or x["seq"] != len(rows) + 1
                    or x["parent_sha256"] != self.parent_hash
                    or x["review_sha256"] != CONTRACT_SHA256
                    or x["prev_sha256"] != prev
                    or x["hash"] != _digest(canonical({
                        k:v for k,v in x.items() if k != "hash"
                    }))):
                raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_CHAIN_CHANGED")
            rows.append(x)
            prev = x["hash"]
        if not rows or rows[0]["action"] != "begin" or rows[0]["step"] != -1:
            raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_BEGIN_MISSING")
        self._validate_sequence(rows)
        return rows

    @staticmethod
    def _validate_sequence(rows: Sequence[Mapping[str, Any]]) -> None:
        done = set()
        pending = None
        reverting = False
        terminal = None
        for i,x in enumerate(rows):
            a, step = x["action"], x["step"]
            if i == 0:
                if a != "begin" or step != -1:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_SEQUENCE_INVALID")
                continue
            if terminal is not None:
                raise A0AtomicTransactionDenied("A0_ATOMIC_REPLAY_AFTER_TERMINAL")
            if a == "intent":
                if reverting or pending is not None or type(step) is not int or step != len(done) or step >= 3:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_INTENT_OUT_OF_ORDER")
                pending = step
            elif a == "installed":
                if reverting or pending != step:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_INSTALLED_WITHOUT_INTENT")
                done.add(step)
                pending = None
            elif a == "rollback_begin":
                if reverting or step != -1:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_ROLLBACK_SEQUENCE_INVALID")
                reverting = True
            elif a == "rollback_verified":
                # A partial interrupted action is also a rollback candidate.
                if not reverting or type(step) is not int or step not in (
                        set(done) | ({pending} if pending is not None else set())):
                    raise A0AtomicTransactionDenied("A0_ATOMIC_UNEXPECTED_ROLLBACK")
                if step in done:
                    done.remove(step)
                else:
                    pending = None
            elif a == "committed":
                if reverting or pending is not None or done != {0, 1, 2} or step != -1:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_PARTIAL_SUCCESS_REJECTED")
                terminal = a
            elif a == "aborted":
                if not reverting or done or pending is not None or step != -1:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_ABORT_NOT_EMPTY")
                terminal = a
            elif a == "requires_review":
                if not reverting or step != -1:
                    raise A0AtomicTransactionDenied("A0_ATOMIC_REVIEW_SEQUENCE_INVALID")
                terminal = a
            else:
                raise A0AtomicTransactionDenied("A0_ATOMIC_UNRECOGNIZED_EVENT")

    def _append(self, action: str, index: int, evidence: Mapping[str, Any]) -> dict[str, Any]:
        rows = self._read_events()
        if not rows and action != "begin":
            raise A0AtomicTransactionDenied("A0_ATOMIC_NO_START")
        record = {
            "version": 1, "seq": len(rows)+1, "action": action,
            "step": index, "parent_sha256": self.parent_hash,
            "review_sha256": CONTRACT_SHA256,
            "detail_sha256": _digest(canonical(dict(evidence))),
            "prev_sha256": rows[-1]["hash"] if rows else "0" * 64,
        }
        record["hash"] = _digest(canonical(record))
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        if action == "begin":
            flags |= os.O_CREAT | os.O_EXCL
        fd = os.open(self.path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise A0AtomicTransactionDenied("A0_ATOMIC_WRITE_JOURNAL_UNTRUSTED")
            raw = canonical(record) + b"\n"
            if os.write(fd, raw) != len(raw):
                raise A0AtomicTransactionDenied("A0_ATOMIC_JOURNAL_SHORT_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        dfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        # Re-parse and validate state transitions after every append.
        self._read_events()
        return record

    def _recover_locked(
        self, *, adapters: A0StageSandboxAdapter,
        rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        # Do not re-run installation, issue approval, or delete anything unless
        # a stage-specific adapter proves the original exact created object.
        if rows[-1]["action"] in ("committed", "aborted", "requires_review"):
            raise A0AtomicTransactionDenied("A0_ATOMIC_ALREADY_TERMINAL")
        actions = [x for x in rows if x["action"] == "intent"]
        already_rolled = {x["step"] for x in rows
                          if x["action"] == "rollback_verified"}
        if not any(x["action"] == "rollback_begin" for x in rows):
            self._append("rollback_begin", -1, {"cause":"interrupted-or-failed"})
        try:
            for index in reversed([x["step"] for x in actions]):
                if index in already_rolled:
                    continue
                if not adapters.verify_absent(index):
                    adapters.rollback_exact(index)
                if not adapters.verify_absent(index):
                    raise A0AtomicTransactionDenied("A0_ATOMIC_ROLLBACK_POSTFLIGHT_FAILED")
                self._append("rollback_verified", index, {"exact_empty":True})
        except BaseException as exc:
            self._append("requires_review", -1, {"cause":type(exc).__name__})
            raise A0AtomicTransactionDenied("A0_ATOMIC_FOREIGN_OR_UNVERIFIED_ROLLBACK") from exc
        self._append("aborted", -1, {"rollback_to_original_absence":True})
        return {"status":"exact_three_stage_rollback_verified",
                "production_mutation":False, "owner_approvals_requested":0}

    def execute(
        self, *, adapters: A0StageSandboxAdapter,
        stage_provider: Callable[[int, frozenset[int]], Mapping[str, Any]],
        at: datetime,
    ) -> dict[str, Any]:
        """One transaction; never executes with anything except 3 exact steps."""
        if not callable(stage_provider) or not isinstance(at, datetime) or at.tzinfo is None:
            raise A0AtomicTransactionDenied("A0_ATOMIC_EXACT_THREE_STEPS_REQUIRED")
        fd = self._open_lock()
        try:
            if self.path.exists() or self.path.is_symlink():
                raise A0AtomicTransactionDenied("A0_ATOMIC_ONE_RELEASE_ALREADY_CLAIMED")
            self._append("begin", -1, {"stages":3})
            try:
                for index, action in enumerate(self.objective.actions):
                    # A machine-only derived proof is issued per step AFTER
                    # the durable root journal attests prior completion.
                    prior = self.bounded.verified_snapshot(action_index=index, at=at)
                    stage = stage_provider(index, prior["verified_prior_steps"])
                    if (not isinstance(stage, Mapping) or set(stage) != {
                        "signed_step", "current_signed_grant",
                    }):
                        raise A0AtomicTransactionDenied("A0_ATOMIC_STAGE_PROOF_FIELDS_CHANGED")
                    grant = verify_current_grant_attestation(
                        objective=self.objective, signed_parent=self.signed_parent,
                        signed_attestation=stage["current_signed_grant"],
                        pinned_public_key=self.pinned_public_key,
                        expected_action_index=index, at=at,
                    )
                    if grant["step_index"] != index:
                        raise A0AtomicTransactionDenied("A0_ATOMIC_UNMATCHED_GRANT")
                    # Root journal is source of truth for predecessor order,
                    # not operator-supplied step completion flags.
                    from orchestrator.pmv4_objective_scope import (
                        verify_proved_objective_step,
                    )
                    observed = {
                        "candidate_sha": self.objective.candidate_sha,
                        "rollback_sha": action.rollback_sha or self.objective.rollback_sha,
                        "freeze_sha256": self.objective.freeze_sha256,
                        "hold_sha256": self.objective.hold_sha256,
                        "scope_sha256": action.scope_sha256,
                        "artifact_sha256": action.artifact_sha256,
                    }
                    verify_proved_objective_step(
                        objective=self.objective,
                        ledger=self.bounded.owner_ledger,
                        signed_parent=self.signed_parent,
                        signed_step=stage["signed_step"],
                        pinned_public_key=self.pinned_public_key,
                        action_index=index, observed=observed, at=at,
                        verified_prior_steps=prior["verified_prior_steps"],
                        consumed_step_claims=prior["consumed_step_claims"],
                    )
                    # The source-only test runs exactly three REAL disposable
                    # effects, never a root mutation. Native final Stage A0
                    # still uses its own existing journal/install primitives.
                    if index != 2:
                        self.bounded.claim(
                            action_index=index, signed_step=stage["signed_step"],
                            observed=observed, at=at,
                        )
                    self._append("intent", index, {
                        "scope_sha256":action.scope_sha256,
                        "signed_step_sha256":_digest(canonical(stage["signed_step"])),
                    })
                    outcome = adapters.apply(index, stage)
                    if (not adapters.verify_installed(index)
                            or not isinstance(outcome, Mapping)):
                        raise A0AtomicTransactionDenied("A0_ATOMIC_STAGE_POSTFLIGHT_FAILED")
                    if index != 2:
                        self.bounded.complete(
                            action_index=index,
                            claim_id=stage["signed_step"]["payload"]["step_claim_id"],
                            native_result={
                                "status":"installed",
                                "scope_sha256":action.scope_sha256,
                                "owner_approval_id":self.signed_parent["payload"]["parent_approval_id"],
                                "production_mutation":False,
                            }, at=at,
                        )
                    self._append("installed", index, {
                        "scope_sha256":action.scope_sha256,
                        "outcome_sha256":_digest(canonical(dict(outcome))),
                    })
                self._append("committed", -1, {"scope_sha256":self.objective.fingerprint})
            except BaseException:
                self._recover_locked(adapters=adapters, rows=self._read_events())
                raise
            return {
                "status":"three_exact_stage_actions_verified_together",
                "owner_approval_id":self.signed_parent["payload"]["parent_approval_id"],
                "atomic_journal_sha256":self._read_events()[-1]["hash"],
                "production_mutation":False, "root_release_enabled":False,
                "additional_human_consents":0,
            }
        finally:
            os.close(fd)

    def reconcile_interrupted(
        self, *, adapters: A0StageSandboxAdapter,
    ) -> dict[str, Any]:
        """Previously claimed, unfinished stage can only be rolled BACK."""
        fd = self._open_lock()
        try:
            rows = self._read_events()
            if not rows:
                raise A0AtomicTransactionDenied("A0_ATOMIC_NEVER_STARTED")
            return self._recover_locked(adapters=adapters, rows=rows)
        finally:
            os.close(fd)

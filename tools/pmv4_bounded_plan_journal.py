"""Crash-durable, fail-closed bounded Owner plan journal; sandbox only.

This is engineering acceptance for a *future* separately governed root-owned
plan consumer. It does not authorize any live root action or trust operator DB
as a production revocation source. A caller may not supply previous-step IDs:
the journal determines them from its verified own append-only evidence.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Mapping

from kernel.signed_owner_release import canonical
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, verify_proved_objective_step,
)
from kernel.pmv4_plan_child_proof import (
    verify_authenticated_owner_objective,
)


class BoundedPlanJournalDenied(PermissionError):
    """Exact plan identity, native evidence or irreversible journal drift."""


_ROOT = Path("/tmp")
_MAX_LOG = 256 * 1024
_ID = re.compile(r"[a-zA-Z0-9._-]{4,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


class BoundedPlanJournal:
    """One signed immutable plan, sequential one-use exact-action claims.

    Source-only, sandbox-only. Future production root integration MUST use
    an immutable root-installed module under root lock; authenticated and
    current Owner grant/revocation controls are NOT supplied here.
    """

    def __init__(
        self, *, directory: Path, objective: BoundedObjective,
        signed_parent: Mapping[str, Any], pinned_public_key: Any,
        owner_ledger: Any, at: datetime,
    ) -> None:
        if (not isinstance(objective, BoundedObjective)
                or not isinstance(signed_parent, Mapping)
                or not isinstance(at, datetime) or at.tzinfo is None
                or not isinstance(directory, Path) or not directory.is_absolute()
                or directory.is_symlink() or not directory.is_dir()
                or _ROOT not in directory.parents
                or not _ID.fullmatch(objective.plan_id)):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_SANDBOX_REQUIRED")
        # Reject /tmp symlink escapes and insecure immediate parent. We never
        # use this path, source module or caller-chosen directory in production.
        directory = directory.resolve(strict=True)
        meta = directory.lstat()
        if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.geteuid()
                or stat.S_IMODE(meta.st_mode) != 0o700
                or directory == _ROOT or _ROOT not in directory.parents):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_UNTRUSTED_SANDBOX")
        self.directory = directory
        self.objective = objective
        self.signed_parent = dict(signed_parent)
        self.parent_hash = _digest(canonical(self.signed_parent))
        self.pinned_public_key = pinned_public_key
        self.owner_ledger = owner_ledger
        self.path = directory / ("owner-plan-" + _digest(
            objective.plan_id.encode("ascii")) + ".jsonl")
        # Plan authority is always revalidated against current revoke/expiry.
        self.parent = verify_authenticated_owner_objective(
            self.signed_parent, objective=objective,
            pinned_public_key=pinned_public_key, at=at, ledger=owner_ledger,
        )

    @contextmanager
    def _locked(self) -> Iterator[int]:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                    or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_FILE_UNTRUSTED")
            yield fd
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self, fd: int) -> list[dict[str, Any]]:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, _MAX_LOG + 1)
        if len(raw) > _MAX_LOG or (raw and not raw.endswith(b"\n")):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_TRUNCATED_OR_OVERLIMIT")
        rows: list[dict[str, Any]] = []
        previous = "0" * 64
        for line in raw.splitlines():
            try:
                row = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_CORRUPT_JSON") from exc
            if (not isinstance(row, dict)
                    or set(row) != {
                        "version", "seq", "event", "parent_hash",
                        "plan_fingerprint", "step", "claim_id",
                        "evidence_sha256", "prev_sha256", "hash",
                    }
                    or row["version"] != 1
                    or type(row["seq"]) is not int
                    or row["seq"] != len(rows) + 1
                    or row["parent_hash"] != self.parent_hash
                    or row["plan_fingerprint"] != self.objective.fingerprint
                    or row["prev_sha256"] != previous
                    or row["hash"] != _digest(canonical({
                        k: v for k, v in row.items() if k != "hash"
                    }))):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_CHAIN_OR_PLAN_CHANGED")
            previous = row["hash"]
            rows.append(row)
        if rows:
            initial = rows[0]
            if (initial["event"] != "enrolled"
                    or initial["step"] != -1
                    or initial["evidence_sha256"] != self.parent_hash
                    or initial["claim_id"] != self.parent["parent_approval_id"]):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_ENROLLMENT_CHANGED")
        return rows

    def _append(self, fd: int, rows: list[dict[str, Any]], *, event: str,
                step: int, claim_id: str, evidence_hash: str) -> dict[str, Any]:
        if not isinstance(evidence_hash, str) or not _HASH.fullmatch(evidence_hash):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_EVIDENCE_HASH_REQUIRED")
        record = {
            "version": 1, "seq": len(rows) + 1, "event": event,
            "parent_hash": self.parent_hash,
            "plan_fingerprint": self.objective.fingerprint,
            "step": step, "claim_id": claim_id,
            "evidence_sha256": evidence_hash,
            "prev_sha256": rows[-1]["hash"] if rows else "0" * 64,
        }
        record["hash"] = _digest(canonical(record))
        encoded = canonical(record) + b"\n"
        if os.lseek(fd, 0, os.SEEK_END) + len(encoded) > _MAX_LOG:
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_OVERLIMIT")
        if os.write(fd, encoded) != len(encoded):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_PARTIAL_WRITE")
        os.fsync(fd)
        dir_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return record

    def _state(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"completed": set(), "claimed": None, "revoked": False}
        completed: set[int] = set()
        claimed: tuple[int, str] | None = None
        revoked = False
        for row in rows[1:]:
            event, step, claim = row["event"], row["step"], row["claim_id"]
            if event == "revoked":
                if step != -1 or revoked or claimed is not None:
                    raise BoundedPlanJournalDenied("PLAN_JOURNAL_REVOKE_SEQUENCE_CHANGED")
                revoked = True
            elif event == "claimed":
                if (revoked or claimed is not None
                        or step != len(completed)
                        or step >= len(self.objective.actions)
                        or claim in {x["claim_id"] for x in rows[1:]
                                    if x is not row and x["event"] == "claimed"}):
                    raise BoundedPlanJournalDenied("PLAN_JOURNAL_CLAIM_SEQUENCE_CHANGED")
                claimed = (step, claim)
            elif event == "completed":
                if (claimed != (step, claim) or step != len(completed)
                        or revoked):
                    raise BoundedPlanJournalDenied("PLAN_JOURNAL_COMPLETION_SEQUENCE_CHANGED")
                completed.add(step)
                claimed = None
            else:
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_EVENT_UNKNOWN")
        return {"completed": completed, "claimed": claimed, "revoked": revoked}

    def _require_active(self, at: datetime) -> None:
        self.parent = verify_authenticated_owner_objective(
            self.signed_parent, objective=self.objective,
            pinned_public_key=self.pinned_public_key, at=at,
            ledger=self.owner_ledger,
        )

    def verified_snapshot(self, *, action_index: int, at: datetime) -> dict[str, Any]:
        """Only the self-verified durable journal supplies previous/replay IDs."""
        if type(action_index) is not int or not 0 <= action_index < len(self.objective.actions):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_INVALID_STEP")
        self._require_active(at)
        with self._locked() as fd:
            rows = self._read(fd)
            if not rows:
                self._append(
                    fd, rows, event="enrolled", step=-1,
                    claim_id=self.parent["parent_approval_id"],
                    evidence_hash=self.parent_hash,
                )
                rows = self._read(fd)
            state = self._state(rows)
            if (state["revoked"] or state["claimed"] is not None
                    or state["completed"] != set(range(action_index))):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_PRIOR_STEPS_NOT_COMPLETE")
            return {
                "verified_prior_steps": frozenset(state["completed"]),
                "consumed_step_claims": frozenset(
                    x["claim_id"] for x in rows if x["event"] == "claimed"
                ),
            }

    def observe_prior(self, *, action_index: int, at: datetime) -> frozenset[int]:
        return self.verified_snapshot(action_index=action_index, at=at)[
            "verified_prior_steps"
        ]

    def claim(self, *, action_index: int, signed_step: Mapping[str, Any],
              observed: Mapping[str, Any], at: datetime) -> dict[str, Any]:
        self._require_active(at)
        with self._locked() as fd:
            rows = self._read(fd)
            if not rows:
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_NOT_ENROLLED")
            state = self._state(rows)
            if (state["revoked"] or state["claimed"] is not None
                    or state["completed"] != set(range(action_index))):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_UNVERIFIED_ORDER_OR_REPLAY")
            verified = verify_proved_objective_step(
                objective=self.objective, ledger=self.owner_ledger,
                signed_parent=self.signed_parent,
                signed_step=dict(signed_step),
                pinned_public_key=self.pinned_public_key,
                action_index=action_index,
                observed=dict(observed),
                at=at,
                verified_prior_steps=frozenset(state["completed"]),
                consumed_step_claims=frozenset(
                    x["claim_id"] for x in rows if x["event"] == "claimed"
                ),
            )
            self._append(
                fd, rows, event="claimed", step=action_index,
                claim_id=verified["step_claim_id"],
                evidence_hash=_digest(canonical(dict(signed_step))),
            )
            return verified

    def complete(self, *, action_index: int, claim_id: str,
                 native_result: Mapping[str, Any], at: datetime) -> str:
        if (type(action_index) is not int
                or not 0 <= action_index < len(self.objective.actions)):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_STEP_OUT_OF_RANGE")
        self._require_active(at)
        # Untrusted receipt contents cannot attest the native installation.
        # A future root adapter MUST retrieve exact receipt hash from native
        # journal under release lock; callers cannot provide it to prod.
        if (not isinstance(native_result, Mapping)
                or native_result.get("status") != "installed"
                or native_result.get("owner_approval_id")
                   != self.parent["parent_approval_id"]
                or native_result.get("production_mutation") is not False
                or native_result.get("scope_sha256")
                   != self.objective.actions[action_index].scope_sha256):
            raise BoundedPlanJournalDenied("PLAN_JOURNAL_NATIVE_RESULT_NOT_VERIFIED")
        with self._locked() as fd:
            rows = self._read(fd)
            state = self._state(rows)
            if state["claimed"] != (action_index, claim_id) or state["revoked"]:
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_NO_CURRENT_CLAIM")
            event = self._append(
                fd, rows, event="completed", step=action_index,
                claim_id=claim_id, evidence_hash=_digest(canonical(dict(native_result))),
            )
            return event["hash"]

    def fail_closed_reopen(self, *, at: datetime) -> None:
        """An unresolved native claim is not silently retried or reissued."""
        self._require_active(at)
        with self._locked() as fd:
            if self._state(self._read(fd))["claimed"] is not None:
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_RECOVERY_REQUIRES_NATIVE_READBACK")

    def revoke(self, *, at: datetime, root_attested_revocation_sha256: str) -> None:
        """SANDBOX only. Production requires independently signed root revocation."""
        self._require_active(at)
        with self._locked() as fd:
            rows = self._read(fd)
            state = self._state(rows)
            if (state["revoked"] or state["claimed"] is not None
                    or not isinstance(root_attested_revocation_sha256, str)
                    or not _HASH.fullmatch(root_attested_revocation_sha256)):
                raise BoundedPlanJournalDenied("PLAN_JOURNAL_REVOCATION_NOT_SAFE")
            self._append(
                fd, rows, event="revoked", step=-1,
                claim_id=self.parent["parent_approval_id"],
                evidence_hash=root_attested_revocation_sha256,
            )

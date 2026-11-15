"""One existing v1 exact Owner release proof -> three A0 actions (SANDBOX).

This is a minimal alternative to the generalized schema-v2 plan issuer.
The original, independently pinned native Owner release signature binds the
WHOLE immutable three-action A0 manifest for 15 minutes. A single release
lock and one-use chained audit commit or exact reverse rollback prevent
partial success from being called complete.

This module cannot be used for live root: production=True always denies.
The independently privileged, root-owned existing-lease consumer and strict
root trust/source/health integration remain separately required.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from kernel.signed_owner_release import canonical
from tools.pmv4_a0_atomic_plan_transaction import (
    A0AtomicSandboxTransaction, A0AtomicTransactionDenied,
    A0StageSandboxAdapter,
)
from tools.pmv4_a0_one_release_v1_proof import (
    verify_existing_v1_whole_transaction,
    exact_v1_release_scopes,
)
from tools.pmv4_stage_a0_one_owner_review import (
    build_reviewed_plan, CONTRACT_SHA256,
)


class OneOwnerV1ExactRelease(A0AtomicSandboxTransaction):
    def __init__(
        self, *, directory: Path, signed_v1_whole_release: Mapping[str, Any],
        pinned_public_key: Any, at: datetime, production: bool = False,
    ) -> None:
        if production:
            raise A0AtomicTransactionDenied(
                "A0_ONE_RELEASE_ROOT_PRODUCTION_CONSUMER_NOT_DEPLOYED"
            )
        if (not isinstance(directory, Path)
                or not directory.is_absolute()
                or not directory.is_dir()
                or directory.is_symlink()
                or directory.resolve(strict=True) != directory
                or Path("/tmp") not in directory.parents
                or not isinstance(signed_v1_whole_release, Mapping)
                or not isinstance(at, datetime) or at.tzinfo is None):
            raise A0AtomicTransactionDenied("A0_ONE_RELEASE_DISPOSABLE_DIR_REQUIRED")
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise A0AtomicTransactionDenied("A0_ONE_RELEASE_JOURNAL_DIR_UNTRUSTED")
        verified = verify_existing_v1_whole_transaction(
            signed=signed_v1_whole_release,
            root_pinned_public_key=pinned_public_key, at=at,
        )
        if verified["approved_action_count"] != 3:
            raise A0AtomicTransactionDenied("A0_ONE_RELEASE_SCOPE_CHANGED")
        self.directory = directory
        self.signed_parent = dict(signed_v1_whole_release)
        self.parent_hash = sha256(canonical(self.signed_parent)).hexdigest()
        self.objective = build_reviewed_plan(
            expires_at=at.replace(microsecond=0) +
            __import__("datetime").timedelta(minutes=15)
        )
        self.bounded = None
        self.pinned_public_key = pinned_public_key
        self.path = directory / "pmv4-stage-a0-atomic-release.jsonl"
        self.lock_path = directory / "pmv4-stage-a0-atomic-release.lock"

    def execute(
        self, *, adapters: A0StageSandboxAdapter, at: datetime,
    ) -> dict[str, Any]:
        verified = verify_existing_v1_whole_transaction(
            signed=self.signed_parent,
            root_pinned_public_key=self.pinned_public_key,
            at=at,
        )
        if verified["scope_sha256"] != exact_v1_release_scopes()["scope_sha256"]:
            raise A0AtomicTransactionDenied("A0_ONE_RELEASE_REVIEW_CHANGED")
        fd = self._open_lock()
        try:
            if self.path.exists() or self.path.is_symlink():
                raise A0AtomicTransactionDenied(
                    "A0_ATOMIC_ONE_RELEASE_ALREADY_CLAIMED"
                )
            self._append("begin", -1, {
                "owner_approval_id": verified["owner_approval_id"],
                "signed_proof_sha256":self.parent_hash,
            })
            try:
                for index, stage in enumerate(
                    exact_v1_release_scopes()["manifest"]["exact_ordered_actions"]
                ):
                    # One native whole-release proof, independently rechecked
                    # before each exact atomic stage. No extra Entra prompts,
                    # operator SQL grants, or v2 signer needed.
                    verify_existing_v1_whole_transaction(
                        signed=self.signed_parent,
                        root_pinned_public_key=self.pinned_public_key,
                        at=at,
                    )
                    self._append("intent", index, {
                        "scope_sha256":stage["scope_sha256"],
                        "artifact_sha256":stage["artifact_sha256"],
                        "signed_proof_sha256":self.parent_hash,
                    })
                    result = adapters.apply(index, {
                        "signed_v1_whole":self.signed_parent,
                        "action":stage["capability"],
                        "scope_sha256":stage["scope_sha256"],
                    })
                    if (not isinstance(result, Mapping)
                            or adapters.verify_installed(index) is not True):
                        raise A0AtomicTransactionDenied(
                            "A0_ONE_RELEASE_STAGE_POSTFLIGHT_INVALID"
                        )
                    self._append("installed", index, {
                        "scope_sha256":stage["scope_sha256"],
                        "receipt_sha256":sha256(canonical(dict(result))).hexdigest(),
                    })
                self._append("committed", -1, {
                    "root_installation_completion":"all_three_or_none",
                    "scope_sha256":verified["scope_sha256"],
                })
            except BaseException:
                self._recover_locked(adapters=adapters, rows=self._read_events())
                raise
            return {
                "status":"three_exact_v1_signed_actions_verified_together",
                "owner_approval_id":verified["owner_approval_id"],
                "single_root_signature_sha256":self.parent_hash,
                "atomic_journal_sha256":self._read_events()[-1]["hash"],
                "production_mutation":False,
                "root_controller_deployed":False,
                "additional_owner_decisions":0,
            }
        finally:
            os.close(fd)

#!/usr/bin/env python3
"""Typed Stage E transaction using the existing native component release ledger.

The generic/financial controller source and its pinned hashes stay unchanged.
This subtype uses the SAME host lock, freeze transaction, component lock,
one-use Owner verifier, receipt store, active pointer, protected snapshots
and crash-recovery journal as the original native release controller.

No shell, root installer, signer, provider write, production CLI or independent
release daemon exists here. Production use requires a separately authenticated,
root-installed pinned entrypoint and concrete root-owned Stage E callbacks.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from implementation.kernel.signed_owner_release import (
    canonical, read_pinned_root_owner_public_key, verify_exact_owner_release,
)
from tools.independent_component_release import (
    ComponentReleaseController, ComponentReleaseDenied, VerifiedRelease,
    PRODUCTION_ROOT, OWNER_TRUST, trusted_file, trusted_dir, _load_json, _atomic_json,
    _replace_json, digest, release_id, PROTECTED,
)
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet

ENTRY = Path(
    "/opt/jason/pmv4-e-trusted/tools/pmv4_e_signed_native_ledger.py"
)
RESOURCE = contract.COMPONENT


def deny(ok: bool, code: str) -> None:
    if not ok:
        raise ComponentReleaseDenied("PMV4_E_NATIVE_" + code)


class StageESignedNativeLedger(ComponentReleaseController):
    """Typed six-unit transaction sharing original native release primitives."""

    def __init__(self, *, source_root: Path, verify_stage_e_preflight=None,
                 **kwargs):
        production = kwargs.get("production", True)
        if production:
            here = Path(__file__)
            info = here.lstat()
            deny(os.geteuid() == 0 and here == ENTRY
                 and here.resolve() == ENTRY and not here.is_symlink()
                 and stat.S_ISREG(info.st_mode) and info.st_uid == 0
                 and info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o444,
                 "ROOT_INSTALLED_PIN_REQUIRED")
            deny(kwargs.get("root") == PRODUCTION_ROOT
                 and Path(source_root).is_absolute()
                 and not Path(source_root).is_symlink()
                 and Path(source_root).parent == Path("/opt/jason/releases"),
                 "IMMUTABLE_SOURCE_ROOT_REQUIRED")
        super().__init__(**kwargs)
        self.source_root = Path(source_root)
        if not production:
            deny(callable(verify_stage_e_preflight),
                 "ISOLATED_PREFLIGHT_CALLBACK_REQUIRED")
        self._test_stage_e_preflight = verify_stage_e_preflight

    def _root_stage_e_preflight(self):
        # The production native root explicitly measures its own health;
        # a caller cannot inject a PASS through a callback.
        if self.production:
            from tools import pmv4_e_root_cutover_preflight as guard
            return guard.evaluate(guard.collect())
        return self._test_stage_e_preflight()

    def _bundle(self, manifest: Mapping[str, Any]) -> Path:
        releases, _, _, _ = self._paths()
        bundle = releases / manifest["candidate_sha"]
        trusted_dir(bundle, production=self.production)
        raw = _load_json(trusted_file(
            bundle / "manifest.json", production=self.production))
        deny(raw == manifest, "MANIFEST_DRIFT")
        scope = _load_json(trusted_file(
            bundle / "source-scope.json", production=self.production))
        try:
            contract.validate(manifest, scope, source_root=self.source_root)
        except (contract.StageEManifestDenied, packet.StageEReleasePacketDenied,
                ValueError, TypeError) as exc:
            raise ComponentReleaseDenied("PMV4_E_NATIVE_SOURCE_SCOPE_DRIFT") from exc
        return bundle

    def _attest_installed_root(self, *, manifest, candidate, previous, verified_bundle):
        # The independent attestor must rehash the exact canonical,
        # ROOT-owned sealed 51-file tree and the root release manifest.
        # No signed Owner grant is accepted on mere source CI or a
        # user-supplied JSON claim of installed root acceptance.
        from tools import pmv4_e_native_root_manifest_attestation as root_attestor
        root_record = root_attestor.inspect(
            source_root=root_attestor.TRUST_ROOT,
            release_dir=verified_bundle,
            production=True,
        )
        deny(
            type(root_record) is dict
            and root_record.get("status") ==
                "root_source_attested_no_release_authority"
            and root_record.get("candidate_sha") == candidate
            and root_record.get("rollback_sha") == previous
            and root_record.get("scope_sha256") ==
                manifest["source_scope_sha256"]
            and root_record.get("manifest_sha256") ==
                digest(canonical(manifest))
            and root_record.get("file_count") ==
                len(packet.REVIEWED_PATHS)
            and root_record.get("production_mutations") is False
            and root_record.get("release_authorized") is False
            and root_record.get("owner_proof_issued") is False,
            "INSTALLED_ROOT_ATTESTATION_NOT_EXACT",
        )

    @staticmethod
    def _bootstrap_record_matches(record, *, manifest, proof, approval_id) -> bool:
        """One Owner signature is bound to BOTH inert bootstrap and release.

        The installed bootstrap journal is never itself a systemd permission.
        The native ledger independently verifies the exact Owner signature
        and requires this separate signed STARTED root receipt as evidence
        that immutable source staging was properly authorized.
        """
        from hashlib import sha256
        from tools import pmv4_e_signed_bootstrap_phase as bootstrap
        return (
            type(record) is dict
            and set(record) == {
                "schema_version", "status", "action", "approval_id",
                "candidate_sha", "rollback_sha", "scope_sha256",
                "manifest_sha256", "freeze_sha256", "source_file_count",
                "signed_owner_proof_sha256", "signed_owner_proof",
                "no_unit_mutations", "native_systemd_release_authorized",
                "started_at", "recovery_required",
            }
            and record["schema_version"] == "1.0"
            and record["status"] == "bootstrap_started"
            and record["action"] == bootstrap.BOOTSTRAP_ACTION
            and record["approval_id"] == approval_id
            and record["candidate_sha"] == manifest["candidate_sha"]
            and record["rollback_sha"] == manifest["rollback_sha"]
            and record["scope_sha256"] == manifest["source_scope_sha256"]
            and record["manifest_sha256"] == digest(canonical(manifest))
            and record["freeze_sha256"] == manifest["freeze_sha256"]
            and record["source_file_count"] == len(packet.REVIEWED_PATHS)
            and record["signed_owner_proof"] == proof
            and record["signed_owner_proof_sha256"] ==
                sha256(canonical(proof)).hexdigest()
            and record["no_unit_mutations"] is True
            and record["native_systemd_release_authorized"] is False
            and record["recovery_required"] is True
        )

    def _attest_bootstrap(self, *, manifest, proof, approval_id) -> None:
        from tools import pmv4_e_signed_bootstrap_phase as bootstrap
        filename="owner-"+approval_id+".json"
        # Never allow the caller or a mutable developer checkout to select
        # a different bootstrap journal directory.
        record=bootstrap.root_record(
            bootstrap.ROOT/filename,production=True)
        deny(self._bootstrap_record_matches(
            record,manifest=manifest,proof=proof,approval_id=approval_id),
            "INERT_ROOT_BOOTSTRAP_OWNER_PROOF_NOT_BOUND")

    def preflight(self, manifest: Mapping[str, Any],
                  signed_approval: Mapping[str, Any], *,
                  at: datetime | None = None):
        """Run solely under native host + component locks; never issue a grant."""
        deny(type(manifest) is dict
             and set(manifest) == contract.MANIFEST_FIELDS,
             "TYPED_SYSTEMD_MANIFEST_REQUIRED")
        releases, receipts, _, _ = self._paths()
        candidate = manifest["candidate_sha"]
        previous = manifest["rollback_sha"]
        if self.production:
            deny(self.source_root.name == candidate
                 and self.source_root.parent == Path("/opt/jason/releases")
                 and not self.source_root.is_symlink(),
                 "SOURCE_REVISION_PATH_UNTRUSTED")
            source_info = self.source_root.lstat()
            deny(stat.S_ISDIR(source_info.st_mode)
                 and source_info.st_uid == 0 and source_info.st_gid == 0
                 and source_info.st_mode & 0o022 == 0,
                 "SOURCE_REVISION_NOT_IMMUTABLE")
        deny(manifest["component_id"] == RESOURCE, "COMPONENT_CHANGED")
        # Stage E is an initial adoption of a non-Compose native component:
        # the live PMv3 source is the physical rollback, NOT a fictitious
        # previously active independent-component release.
        deny(self._active(RESOURCE) is None, "ALREADY_RELEASED")
        deny(self.observe_component(RESOURCE) == previous,
             "PHYSICAL_ROLLBACK_CHANGED")
        verified_bundle = self._bundle(manifest)
        if self.production:
            self._attest_installed_root(
                manifest=manifest, candidate=candidate, previous=previous,
                verified_bundle=verified_bundle,
            )
        gate = self._root_stage_e_preflight()
        deny(type(gate) is dict
             and gate.get("status") ==
                 "read_only_root_preflight_source_conditions_passed"
             and gate.get("production_mutations") is False
             and gate.get("owner_release_authorized") is False
             and gate.get("pmv3_retirement_authorized") is False
             and gate.get("legacy_triggers_verified") == 6
             and gate.get("replacement_triggers_verified_inert") == 6,
             "CURRENT_ROOT_PRECUTOVER_GATE_DENIED")
        deny(self.verify_source_and_ci(candidate) is True,
             "SOURCE_OR_PROTECTED_CI_UNVERIFIED")
        baseline = self._verify_protected_snapshot()
        self._freeze_bytes(manifest)
        consumed = self._check_pending(receipts)
        key = (read_pinned_root_owner_public_key(OWNER_TRUST)
               if self.production else self._test_key)
        grant = verify_exact_owner_release(
            signed_approval, public_key=key,
            expected_release_id=release_id(candidate),
            expected_candidate_sha=candidate,
            expected_rollback_sha=previous,
            expected_scope_sha256=manifest["source_scope_sha256"],
            expected_manifest_sha256=digest(canonical(manifest)),
            expected_freeze_sha256=manifest["freeze_sha256"],
            consumed_ids=consumed,
            at=at or datetime.now(timezone.utc),
        )
        if self.production:
            self._attest_bootstrap(
                manifest=manifest,proof=signed_approval,approval_id=grant["approval_id"],
            )
        return (VerifiedRelease(
            RESOURCE, candidate, previous, grant["approval_id"],
            digest(canonical(manifest)), manifest["source_scope_sha256"],
        ), verified_bundle, baseline)

    def _journal(self, release, manifest, baseline, signed_approval):
        return {
            "schema_version": "1.0",
            "state": "started", "component_id": RESOURCE,
            "release_id": release_id(release.candidate_sha),
            "approval_id": release.approval_id,
            "candidate_sha": release.candidate_sha,
            "rollback_sha": release.rollback_sha,
            "manifest_sha256": release.manifest_sha256,
            "scope_sha256": release.scope_sha256,
            "freeze_sha256": manifest["freeze_sha256"],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "protected_before": dict(baseline),
            "signed_owner_proof": dict(signed_approval),
        }

    def _native_lock(self):
        # Return the exact original lock path after verifying the release dirs.
        _, _, control, _ = self._paths()
        p = control / "component-release.lock"
        trusted_file(p, production=self.production,
                     max_bytes=4096, allow_owner_write=True)
        return p

    def promote(self, manifest: Mapping[str, Any],
                signed_approval: Mapping[str, Any]) -> dict[str, Any]:
        """Use the original host, component and freeze boundaries."""
        deny(type(manifest) is dict and set(manifest) == contract.MANIFEST_FIELDS,
             "TYPED_SYSTEMD_MANIFEST_REQUIRED")
        with self.host_transaction():
            with self._native_lock().open("rb") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ComponentReleaseDenied("COMPONENT_TRANSACTION_BUSY") from exc
                # Source/CI and Owner preflight must see the same freeze
                # boundary as activation, not a pre-lock approximation.
                with self.freeze_transaction(manifest["freeze_sha256"]):
                    verified, bundle, before = self.preflight(
                        manifest, signed_approval)
                    *_, active = self._paths()
                    _, receipts, _, _ = self._paths()
                    receipt = receipts / ("owner-" + verified.approval_id + ".json")
                    journal = self._journal(
                        verified, manifest, before, signed_approval)
                    _atomic_json(receipt, journal)  # Crash recovery begins HERE.
                    prior = self.source_root.parent / verified.rollback_sha
                    try:
                        self.activate_component(bundle, manifest)
                        deny(self.observe_component(RESOURCE) ==
                             verified.candidate_sha,
                             "ACTIVATION_READBACK_FAILED")
                        deny(self.verify_component(bundle, manifest) is True,
                             "LIVE_SIX_UNIT_ACCEPTANCE_FAILED")
                        deny(self._same_protected(
                            before, self._verify_protected_snapshot()),
                            "PROTECTED_CONTAINERS_CHANGED")
                    except BaseException:
                        try:
                            self.restore_component(prior, manifest)
                            deny(self.observe_component(RESOURCE) ==
                                 verified.rollback_sha,
                                 "ROLLBACK_READBACK_FAILED")
                            deny(self.verify_component(prior, manifest) is True,
                                 "ROLLBACK_ACCEPTANCE_FAILED")
                            deny(self._same_protected(
                                before, self._verify_protected_snapshot()),
                                "PROTECTED_ROLLBACK_DRIFT")
                            journal["state"] = "rolled_back"
                            journal["finished_at"] = datetime.now(
                                timezone.utc).isoformat()
                            _replace_json(receipt, journal)
                        except BaseException:
                            # Unresolved STARTED receipt blocks other releases.
                            pass
                        raise
                self._freeze_bytes(manifest)
                pointer = active / (RESOURCE + ".json")
                deny(not pointer.exists() and not pointer.is_symlink(),
                     "ACTIVE_POINTER_CONFLICT")
                _atomic_json(pointer, {
                    "component_id": RESOURCE,
                    "candidate_sha": verified.candidate_sha,
                    "manifest_sha256": verified.manifest_sha256,
                })
                journal["state"] = "accepted"
                journal["finished_at"] = datetime.now(
                    timezone.utc).isoformat()
                _replace_json(receipt, journal)
                return {
                    "status": "native_stage_e_six_unit_accepted",
                    "candidate_sha": verified.candidate_sha,
                    "rollback_sha": verified.rollback_sha,
                    "approval_id": verified.approval_id,
                    "protected_services_changed": False,
                }

    def recover_interrupted_rollback(self) -> dict[str, Any]:
        """Rollback only the one outstanding original signed Stage E receipt."""
        with self.host_transaction():
            with self._native_lock().open("rb") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ComponentReleaseDenied("COMPONENT_TRANSACTION_BUSY") from exc
                releases, receipts, _, active = self._paths()
                pending = []
                for p in receipts.iterdir():
                    row = _load_json(trusted_file(
                        p, production=self.production, allow_owner_write=True))
                    deny(p.name == "owner-" + str(row.get("approval_id")) + ".json",
                         "RECEIPT_ID_DRIFT")
                    deny(row.get("state") in
                         ("started", "accepted", "rolled_back"),
                         "RECEIPT_UNKNOWN_STATE")
                    if row["state"] == "started":
                        pending.append((p, row))
                if not pending:
                    return {"status": "nothing_pending", "production_mutation": False}
                deny(len(pending) == 1, "MULTIPLE_OUTSTANDING_RELEASES")
                receipt, row = pending[0]
                candidate, rollback = row.get("candidate_sha"), row.get("rollback_sha")
                deny(row.get("component_id") == RESOURCE
                     and isinstance(candidate, str) and len(candidate) == 40
                     and isinstance(rollback, str) and len(rollback) == 40,
                     "RECOVERY_IDENTITY_DRIFT")
                manifest = _load_json(trusted_file(
                    releases / candidate / "manifest.json",
                    production=self.production))
                deny(type(manifest) is dict and
                     set(manifest) == contract.MANIFEST_FIELDS
                     and manifest.get("component_id") == RESOURCE
                     and manifest.get("candidate_sha") == candidate
                     and manifest.get("rollback_sha") == rollback
                     and row.get("manifest_sha256") == digest(canonical(manifest))
                     and row.get("scope_sha256") ==
                         manifest.get("source_scope_sha256")
                     and row.get("freeze_sha256") ==
                         manifest.get("freeze_sha256")
                     and row.get("release_id") == release_id(candidate),
                     "RECOVERY_SCOPE_DRIFT")
                self._bundle(manifest)
                key = (read_pinned_root_owner_public_key(OWNER_TRUST)
                       if self.production else self._test_key)
                try:
                    started = datetime.fromisoformat(row["started_at"])
                except (ValueError, TypeError, KeyError) as exc:
                    raise ComponentReleaseDenied(
                        "PMV4_E_NATIVE_START_TIME_INVALID") from exc
                grant = verify_exact_owner_release(
                    row.get("signed_owner_proof"), public_key=key,
                    expected_release_id=release_id(candidate),
                    expected_candidate_sha=candidate,
                    expected_rollback_sha=rollback,
                    expected_scope_sha256=manifest["source_scope_sha256"],
                    expected_manifest_sha256=digest(canonical(manifest)),
                    expected_freeze_sha256=manifest["freeze_sha256"],
                    at=started,
                )
                deny(grant["approval_id"] == row.get("approval_id"),
                     "RECOVERY_APPROVAL_DRIFT")
                before = row.get("protected_before")
                deny(isinstance(before, dict) and
                     set(before) == set(PROTECTED) and
                     self._same_protected(before,
                                          self._verify_protected_snapshot()),
                     "RECOVERY_PROTECTED_DRIFT")
                deny(self._active(RESOURCE) in (None, candidate),
                     "RECOVERY_ACTIVE_POINTER_DRIFT")
                deny(self.observe_component(RESOURCE) in
                     (rollback, candidate, None),
                     "RECOVERY_TRIGGER_STATE_DRIFT")
                self._freeze_bytes(manifest)
                previous = self.source_root.parent / rollback
                with self.freeze_transaction(manifest["freeze_sha256"]):
                    self.restore_component(previous, manifest)
                    deny(self.observe_component(RESOURCE) == rollback,
                         "RECOVERY_ROLLBACK_READBACK_FAILED")
                    deny(self.verify_component(previous, manifest) is True,
                         "RECOVERY_ACCEPTANCE_FAILED")
                    deny(self._same_protected(
                        before, self._verify_protected_snapshot()),
                        "RECOVERY_PROTECTED_CHANGED")
                self._freeze_bytes(manifest)
                pointer = active / (RESOURCE + ".json")
                if pointer.exists() or pointer.is_symlink():
                    deny(self._active(RESOURCE) == candidate
                         and pointer.is_file() and not pointer.is_symlink(),
                         "RECOVERY_POINTER_DRIFT")
                    pointer.unlink()
                row["state"] = "rolled_back"
                row["reconciled"] = True
                row["finished_at"] = datetime.now(timezone.utc).isoformat()
                _replace_json(receipt, row)
                return {
                    "status": "native_stage_e_six_unit_rollback_verified",
                    "candidate_sha": candidate, "rollback_sha": rollback,
                    "approval_id": grant["approval_id"],
                    "protected_services_changed": False,
                }

#!/usr/bin/env python3
"""Exact one-use Owner-signed *inert* Stage E root-bootstrap admission.

This is not a second release manager or a root installer. It is the missing
ordering boundary: stage root trust only AFTER an independently verified exact
Owner signature and durable bootstrap STARTED journal, but BEFORE the native
systemd ledger attempts its independent installed-root attestation.

Only the existing native ComponentReleaseController may subsequently retire
the six PMv3 triggers. This module never starts/stops units, unfreezes,
restarts services, writes providers, or issues any Owner authorization.
Production requires a separately installed, root-owned pinned entrypoint.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Any,Callable,Mapping

from implementation.kernel.signed_owner_release import (
    canonical,read_pinned_root_owner_public_key,verify_exact_owner_release,
)
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools.independent_component_release import (
    _atomic_json,_load_json,trusted_file,release_id,OWNER_TRUST,
)

ROOT=Path("/var/lib/jason/independent-component-release/stage-e-bootstrap")
ENTRY=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_signed_bootstrap_phase.py")
NATIVE_RECEIPTS=Path("/var/lib/jason/independent-component-release/receipts")
BOOTSTRAP_ACTION="pmv4_e_stage_exact_signed_inert_root_v1"
FIELDS=frozenset({
    "schema_version","request_id","action","candidate_sha",
    "rollback_sha","scope_sha256","manifest_sha256","freeze_sha256",
    "signed_owner_proof",
})


class StageEBootstrapDenied(PermissionError):
    pass


def require(ok:bool, reason:str)->None:
    if not ok:
        raise StageEBootstrapDenied("PMV4_E_SIGNED_BOOTSTRAP_"+reason)


def root_record(path:Path,*,production:bool)->dict[str,Any]:
    try:
        metadata=path.lstat()
        require(stat.S_ISREG(metadata.st_mode)
                and not path.is_symlink()
                and metadata.st_nlink==1
                and 0<metadata.st_size<=32768
                and metadata.st_mode & 0o022==0,
                "RECORD_OBJECT_UNTRUSTED")
        if production:
            require(metadata.st_uid==0 and metadata.st_gid==0
                    and stat.S_IMODE(metadata.st_mode)==0o600,
                    "RECORD_OWNER_OR_MODE_UNTRUSTED")
        return _load_json(path.read_bytes())
    except StageEBootstrapDenied:
        raise
    except (OSError,PermissionError) as exc:
        raise StageEBootstrapDenied(
            "PMV4_E_SIGNED_BOOTSTRAP_RECORD_UNAVAILABLE") from exc


class SignedInertBootstrap:
    """One signed exact Stage E trust-stage permit, never six-unit authority."""

    def __init__(
        self,*,root:Path=ROOT,
        source_root:Path,
        host_lock_held:Callable[[],bool],
        freeze_lock_held:Callable[[],bool],
        legacy_active:Callable[[],bool],
        replacements_inert:Callable[[],bool],
        marker_absent:Callable[[],bool],
        source_ci_verified:Callable[[str],bool],
        production:bool=True,
        test_owner_public_key:Any=None,
        native_receipts:Path=NATIVE_RECEIPTS,
    ):
        if production:
            here=Path(__file__)
            meta=here.lstat()
            require(os.geteuid()==0 and here==ENTRY
                    and here.resolve()==ENTRY
                    and not here.is_symlink()
                    and stat.S_ISREG(meta.st_mode)
                    and meta.st_uid==meta.st_gid==0
                    and stat.S_IMODE(meta.st_mode)==0o444
                    and Path(root)==ROOT
                    and Path(native_receipts)==NATIVE_RECEIPTS,
                    "CANONICAL_ROOT_INSTALL_REQUIRED")
        for cb in (host_lock_held,freeze_lock_held,
                   legacy_active,replacements_inert,marker_absent,
                   source_ci_verified):
            require(callable(cb),"HOST_EVIDENCE_CALLBACK_REQUIRED")
        self.root=Path(root)
        self.source_root=Path(source_root)
        self.native_receipts=Path(native_receipts)
        self.host_lock_held=host_lock_held
        self.freeze_lock_held=freeze_lock_held
        self.legacy_active=legacy_active
        self.replacements_inert=replacements_inert
        self.marker_absent=marker_absent
        self.source_ci_verified=source_ci_verified
        self.production=production
        self.test_owner_public_key=test_owner_public_key

    def _checks(self)->None:
        require(self.host_lock_held() is True and
                self.freeze_lock_held() is True,
                "NATIVE_SHARED_HOST_AND_FREEZE_LOCKS_REQUIRED")
        require(self.marker_absent() is True and
                self.legacy_active() is True and
                self.replacements_inert() is True,
                "LIVE_PRECUTOVER_STATE_NOT_INERT")
        for p in (self.root,self.native_receipts):
            meta=p.lstat()
            require(stat.S_ISDIR(meta.st_mode) and
                    not p.is_symlink() and meta.st_mode&0o022==0,
                    "ROOT_JOURNAL_DIRECTORY_UNTRUSTED")
            if self.production:
                require(meta.st_uid==meta.st_gid==0
                        and stat.S_IMODE(meta.st_mode)==0o700,
                        "ROOT_JOURNAL_OWNER_OR_MODE_UNTRUSTED")

    def _used(self)->frozenset[str]:
        used=set()
        for directory in (self.root,self.native_receipts):
            for path in directory.iterdir():
                require(path.name.startswith("owner-") and
                        path.suffix==".json",
                        "UNREVIEWED_JOURNAL_ENTRY")
                record=root_record(path,production=self.production)
                name=record.get("approval_id")
                require(type(name) is str and path.name=="owner-"+name+".json",
                        "JOURNAL_APPROVAL_ID_CHANGED")
                used.add(name)
        return frozenset(used)

    def validate(self,request:Mapping[str,Any],*,at:datetime|None=None)->dict[str,Any]:
        self._checks()
        require(type(request) is dict and set(request)==FIELDS
                and request["schema_version"]=="1.0"
                and request["action"]==BOOTSTRAP_ACTION
                and isinstance(request["signed_owner_proof"],dict),
                "REQUEST_SCHEMA_OR_ACTION_CHANGED")
        candidate=request["candidate_sha"]
        rollback=request["rollback_sha"]
        try:
            reviewed=contract.draft(
                candidate_sha=candidate,rollback_sha=rollback,
                source_root=self.source_root)
        except (contract.StageEManifestDenied,
                packet.StageEReleasePacketDenied,
                ValueError,TypeError) as exc:
            raise StageEBootstrapDenied(
                "PMV4_E_SIGNED_BOOTSTRAP_REVIEWED_SOURCE_NOT_EXACT") from exc
        manifest=reviewed["manifest"]
        require(request["scope_sha256"]==manifest["source_scope_sha256"]
                and request["manifest_sha256"]==reviewed["manifest_sha256"]
                and request["freeze_sha256"]==manifest["freeze_sha256"]
                and request["request_id"]==release_id(candidate),
                "REVIEWED_EXACT_RELEASE_BINDING_CHANGED")
        require(self.source_ci_verified(candidate) is True,
                "PROTECTED_SOURCE_CI_NOT_VERIFIED")
        key=(read_pinned_root_owner_public_key(OWNER_TRUST)
             if self.production else self.test_owner_public_key)
        verified=verify_exact_owner_release(
            request["signed_owner_proof"],public_key=key,
            expected_release_id=release_id(candidate),
            expected_candidate_sha=candidate,
            expected_rollback_sha=rollback,
            expected_scope_sha256=manifest["source_scope_sha256"],
            expected_manifest_sha256=reviewed["manifest_sha256"],
            expected_freeze_sha256=manifest["freeze_sha256"],
            at=at or datetime.now(timezone.utc),
            consumed_ids=self._used(),
        )
        return {
            "schema_version":"1.0",
            "status":"owner_signed_inert_bootstrap_preflight_only",
            "action":BOOTSTRAP_ACTION,
            "approval_id":verified["approval_id"],
            "candidate_sha":candidate,
            "rollback_sha":rollback,
            "scope_sha256":manifest["source_scope_sha256"],
            "manifest_sha256":reviewed["manifest_sha256"],
            "freeze_sha256":manifest["freeze_sha256"],
            "source_file_count":reviewed["source_files_verified"],
            "signed_owner_proof_sha256":sha256(canonical(
                request["signed_owner_proof"])).hexdigest(),
            "signed_owner_proof":request["signed_owner_proof"],
            "no_unit_mutations":True,
            "native_systemd_release_authorized":False,
        }

    def begin(self,request:Mapping[str,Any],*,at:datetime|None=None)->dict[str,Any]:
        """Write one durable BOOTSTRAP STARTED record; units remain untouched."""
        proof=self.validate(request,at=at)
        record={
            **proof,
            "status":"bootstrap_started",
            "started_at":(at or datetime.now(timezone.utc)).isoformat(),
            "recovery_required":True,
        }
        name="owner-"+proof["approval_id"]+".json"
        _atomic_json(self.root/name,record)
        return {
            "status":"bootstrap_started_no_systemd_mutation",
            "approval_id":record["approval_id"],
            "candidate_sha":record["candidate_sha"],
            "scope_sha256":record["scope_sha256"],
            "native_systemd_release_authorized":False,
            "production_unit_changes":False,
        }

    def signed_started(self,*,candidate_sha:str,
                       scope_sha256:str,approval_id:str)->bool:
        """Stager callback: prove prior ROOT-durable same-action STARTED."""
        self._checks()
        try:
            record=root_record(
                self.root/("owner-"+approval_id+".json"),
                production=self.production)
        except StageEBootstrapDenied:
            return False
        return (
            record.get("status")=="bootstrap_started"
            and record.get("action")==BOOTSTRAP_ACTION
            and record.get("candidate_sha")==candidate_sha
            and record.get("scope_sha256")==scope_sha256
            and record.get("approval_id")==approval_id
            and record.get("native_systemd_release_authorized") is False
            and record.get("no_unit_mutations") is True
        )

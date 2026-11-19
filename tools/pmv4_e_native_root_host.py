#!/usr/bin/env python3
"""Concrete Stage E root host for the EXISTING signed native release ledger.

This module owns no signature issuer or release engine. Original root
ComponentReleaseController issues and consumes exact Owner proof, shared
host/freeze locks, immutable STARTED/ACCEPTED/ROLLED_BACK receipts and
interrupted rollback. StageEUnitAdapter controls the exact six reviewed
systemd controls through StageERootBridge and ExactSystemdSurface.

Source only until pinned under /opt/jason/pmv4-e-trusted by the independently
authorized root bootstrap. Does not implement a root CLI, sudo escalation,
Docker/provider mutation, service restart, reboot, or network operation.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any,Callable,Mapping

from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_native_root_manifest_attestation as rootattest
from tools import pmv4_e_native_systemd_adapter as adapter
from tools import pmv4_e_replacement_unit_bundle as bundle
from tools import pmv4_e_scheduler_parity as parity
from tools import pmv4_e_exact_code_transaction as code
from tools import pmv4_e_signed_bootstrap_phase as bootstrap
from tools import pmv4_e_unit_admission as admission
from tools import pmv4_e_retirement_readiness as retirement
from tools import pmv4_e_ticket_owner_readback as ownerreadback
from tools.independent_component_host_adapter import IndependentComponentHost
from tools.independent_component_release import (
    PROTECTED, OWNER_TRUST, PMV3_FREEZE,
)
from implementation.kernel.signed_owner_release import (
    canonical,read_pinned_root_owner_public_key,verify_exact_owner_release,
)

ENTRY=Path("/opt/jason/pmv4-e-trusted/tools/pmv4_e_native_root_host.py")
TRUST=Path("/opt/jason/pmv4-e-trusted")
NATIVE_ROOT=Path("/var/lib/jason/independent-component-release")
RECEIPTS=NATIVE_ROOT/"receipts"
BEFORE=NATIVE_ROOT/"stage-e-physical-before"
STEPS=NATIVE_ROOT/"stage-e-step-audit"
MARKER=admission.ACCEPTED
CURRENT=Path("/opt/jason/current")
FREEZE=PMV3_FREEZE
RELEASE_RE=re.compile(r"^owner-mcp-[0-9a-f]{32}$")
SHA40=re.compile(r"^[0-9a-f]{40}$")


class StageEHostDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:
        raise StageEHostDenied("PMV4_E_NATIVE_HOST_"+reason)


def digest(data:bytes)->str:
    return sha256(data).hexdigest()


def read_json(path:Path,*,max_bytes:int=200000)->dict[str,Any]:
    try:
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_nlink==1 and 0<meta.st_size<=max_bytes
             and meta.st_mode&0o022==0,
             "PROTECTED_JSON_FILE_UNTRUSTED")
        raw=path.read_bytes()
        need(len(raw)==meta.st_size,"PROTECTED_JSON_CHANGED")
        obj=json.loads(raw)
        need(type(obj) is dict,"PROTECTED_JSON_NOT_OBJECT")
        return obj
    except StageEHostDenied:
        raise
    except (OSError,TypeError,ValueError) as exc:
        raise StageEHostDenied("PMV4_E_NATIVE_HOST_PROTECTED_JSON_UNAVAILABLE") from exc


def sealed_dir(path:Path,*,production:bool)->None:
    meta=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(meta.st_mode)
         and meta.st_mode&0o022==0,"ROOT_JOURNAL_PATH_UNTRUSTED")
    if production:
        need(meta.st_uid==0 and meta.st_gid==0
             and stat.S_IMODE(meta.st_mode)==0o700,
             "ROOT_JOURNAL_NOT_PRIVATE")


class NativeStageEHost:
    """Typed host callbacks consumed by the EXISTING signed Stage E ledger."""

    def __init__(
        self,*,manifest:Mapping[str,Any],scope:Mapping[str,Any],
        owner_proof:Mapping[str,Any],
        production:bool=True,
        core_host:Any=None,code_switch:Any=None,systemd:Any=None,
        receipt_dir:Path=RECEIPTS,before_dir:Path=BEFORE,
        step_dir:Path=STEPS,marker:Path=MARKER,
        current:Path=CURRENT,freeze:Path=FREEZE,
        source_root:Path=TRUST,
        owner_evidence:Callable[[],dict]|None=None,
        scan_evidence:Callable[[],dict]|None=None,
        test_owner_public_key:Any=None,
        test_before_evidence:Callable[[],adapter.Before]|None=None,
    ):
        if production:
            here=Path(__file__)
            meta=here.lstat()
            need(os.geteuid()==0 and here==ENTRY and here.resolve()==ENTRY
                 and not here.is_symlink() and stat.S_ISREG(meta.st_mode)
                 and meta.st_uid==meta.st_gid==0
                 and stat.S_IMODE(meta.st_mode)==0o444,
                 "ROOT_INSTALLED_ENTRY_REQUIRED")
            need(core_host is None and code_switch is None
                 and systemd is None and owner_evidence is None
                 and scan_evidence is None
                 and test_owner_public_key is None
                 and test_before_evidence is None
                 and receipt_dir==RECEIPTS and before_dir==BEFORE
                 and step_dir==STEPS and marker==MARKER
                 and current==CURRENT and freeze==FREEZE
                 and source_root==TRUST,
                 "PRODUCTION_HOST_DEPENDENCY_INJECTION_DENIED")
        need(type(manifest) is dict and type(scope) is dict
             and isinstance(owner_proof,dict),
             "EXACT_SIGNED_MANIFEST_REQUIRED")
        try:
            typed=contract.validate(manifest,scope,source_root=source_root)
        except (contract.StageEManifestDenied,
                packet.StageEReleasePacketDenied,ValueError,TypeError) as exc:
            raise StageEHostDenied(
                "PMV4_E_NATIVE_HOST_REVIEWED_SCOPE_NOT_EXACT") from exc
        need(typed["manifest_sha256"]==digest(canonical(manifest)),
             "CANONICAL_MANIFEST_DIGEST_DRIFT")
        need(SHA40.fullmatch(manifest["candidate_sha"]) is not None
             and SHA40.fullmatch(manifest["rollback_sha"]) is not None,
             "INVALID_CANDIDATE_OR_ROLLBACK")
        proof=(owner_proof.get("payload") or {})
        approval_id=proof.get("approval_id")
        need(type(approval_id) is str
             and RELEASE_RE.fullmatch(approval_id) is not None,
             "AUTHENTICATED_OWNER_PROOF_ID_MISSING")
        self.manifest=dict(manifest)
        self.scope=dict(scope)
        self.owner_proof=dict(owner_proof)
        self.approval_id=approval_id
        self.source_root=Path(source_root)
        self.receipt_dir=Path(receipt_dir)
        self.before_dir=Path(before_dir)
        self.step_dir=Path(step_dir)
        self.marker=Path(marker)
        self.current=Path(current)
        self.freeze=Path(freeze)
        self.production=production
        self.code_test_public_key=test_owner_public_key
        self.test_before_evidence=test_before_evidence
        need(production or test_owner_public_key is not None,
             "ISOLATED_OWNER_KEY_REQUIRED")
        self.core_host=(IndependentComponentHost(production=True)
                        if production else core_host)
        need(self.core_host is not None,
             "PREINSTALLED_NATIVE_HOST_REQUIRED")
        if production:
            from tools.pmv4_e_systemd_root_ops import ExactSystemdSurface
            self.systemd=ExactSystemdSurface(production=True)
        else:
            self.systemd=systemd
        need(self.systemd is not None,
             "SIGNED_SYSTEMD_INTERFACE_REQUIRED")
        self.owner_evidence=(ownerreadback.inspect
                             if production else owner_evidence)
        self.scan_evidence=(retirement.scan_summary
                            if production else scan_evidence)
        need(callable(self.owner_evidence) and callable(self.scan_evidence),
             "LIVE_TICKET_EVIDENCE_REQUIRED")
        self.host_locked=False
        self.freeze_locked=False
        self.before=None
        self.parity_passed=False
        self._first_scan=None
        self._approved_unit_hashes=None
        self.code=(code.StageECodeTransaction(
            signed_started=lambda:self.native_started_receipt_verified(
                self.manifest["candidate_sha"],
                self.manifest["rollback_sha"],
                self.manifest["source_scope_sha256"]),
            shared_host_lock=lambda:self.host_locked,
            freeze_lock=lambda:self.freeze_locked,
            replacement_marker_absent=lambda:not self._marker_present(),
            production=True,
        ) if production else code_switch)
        need(self.code is not None,
             "DURABLE_CODE_BEFORE_IMAGE_REQUIRED")

    @contextmanager
    def host_transaction(self):
        need(not self.host_locked,"HOST_LOCK_REENTRANT")
        with self.core_host.host_transaction():
            self.host_locked=True
            try:yield
            finally:self.host_locked=False

    @contextmanager
    def freeze_transaction(self,expected:str):
        need(self.host_locked and not self.freeze_locked,
             "HOST_FREEZE_ORDER_INVALID")
        with self.core_host.freeze_transaction(expected):
            self.freeze_locked=True
            try:yield
            finally:self.freeze_locked=False

    def _verify_boundary(self)->None:
        need(self.host_locked and self.freeze_locked,
             "SIGNED_NATIVE_HOST_AND_FREEZE_LOCK_REQUIRED")

    def _marker_present(self)->bool:
        return self.marker.exists() or self.marker.is_symlink()

    def _source_revision(self)->str:
        p=self.current.resolve()
        need(p.parent==Path("/opt/jason/releases") or not self.production,
             "CURRENT_RELEASE_PATH_UNTRUSTED")
        need(SHA40.fullmatch(p.name) is not None,
             "CURRENT_SOURCE_SHA_UNTRUSTED")
        return p.name

    def _protected_hash(self)->str:
        data=self.core_host.protected()
        need(type(data) is dict and set(data)==set(PROTECTED),
             "PROTECTED_RUNTIME_FINGERPRINT_UNAVAILABLE")
        return digest(canonical(data))

    def _ticket_owner(self)->dict[str,Any]:
        doc=self.owner_evidence()
        need(type(doc) is dict
             and doc.get("status")==
                 "live_external_ticket_core_exclusive_owner_verified"
             and doc.get("unique_owner") is True
             and doc.get("exclusive_owner_count")==1
             and doc.get("production_mutations") is False,
             "CURRENT_UNIQUE_TICKET_DISPATCH_OWNER_MISSING")
        return doc

    def _scan(self)->dict[str,Any]:
        doc=self.scan_evidence()
        need(type(doc) is dict and doc.get("status")=="fresh"
             and doc.get("duplicate_items")==0
             and isinstance(doc.get("observed_at"),str),
             "REAL_TICKET_SCAN_NOT_FRESH_OR_DUPLICATED")
        return doc

    def root_install_verified(self)->bool:
        if self.production:
            witness=rootattest.inspect(
                source_root=rootattest.TRUST_ROOT,
                release_dir=NATIVE_ROOT/"releases"/self.manifest["candidate_sha"],
                production=True,
            )
            need(witness["manifest_sha256"]==digest(canonical(self.manifest))
                 and witness["scope_sha256"]==
                     self.manifest["source_scope_sha256"]
                 and witness["candidate_sha"]==
                     self.manifest["candidate_sha"],
                 "INDEPENDENT_ROOT_SOURCE_NOT_ATTESTED")
        return True

    def exclusive_host_lock_held(self)->bool:
        return self.host_locked

    def freeze_lock_held(self)->bool:
        return self.freeze_locked

    def old_user_units(self):return adapter.OLD_USER
    def old_root_units(self):return adapter.OLD_ROOT
    def new_user_units(self):return adapter.NEW_USER
    def new_root_units(self):return adapter.NEW_ROOT
    def all_user_triggers(self):return adapter.OLD_USER+adapter.NEW_USER
    def all_root_triggers(self):return adapter.OLD_ROOT+adapter.NEW_ROOT

    def read_protected_before(self)->adapter.Before:
        self._verify_boundary()
        if self.test_before_evidence is not None:
            before=self.test_before_evidence()
            need(isinstance(before,adapter.Before),
                 "ISOLATED_BEFORE_NOT_TYPED")
            adapter.assert_exact_before(before)
            need(before.source_sha==self.manifest["rollback_sha"],
                 "ROLLBACK_BASELINE_CHANGED")
            self.before=before
            self._first_scan=self._scan()["observed_at"]
            return before
        active=set()
        enabled=set()
        for user,names in (
            (True,self.all_user_triggers()),(False,self.all_root_triggers()),
        ):
            for name in names:
                status=self.systemd.status(name,user=user)
                if status[0]=="active":active.add(name)
                if status[1]=="enabled":enabled.add(name)
        policy=code.read_exact(self.code.targets[code.POLICY])
        freeze=code.read_exact(self.freeze)
        before=adapter.Before(
            active=frozenset(active),enabled=frozenset(enabled),
            policy_sha256=digest(policy),
            source_sha=self._source_revision(),
            freeze_sha256=digest(freeze),
            protected_fingerprint=self._protected_hash(),
            claims_fingerprint=digest(canonical(self._ticket_owner())),
            marker_present=self._marker_present(),
        )
        adapter.assert_exact_before(before)
        need(before.source_sha==self.manifest["rollback_sha"]
             and before.freeze_sha256==self.manifest["freeze_sha256"]
             and before.policy_sha256==packet.EXPECTED_PRIOR_ROOT_POLICY,
             "LIVE_PROTECTED_BEFORE_CHANGED")
        self.before=before
        self._first_scan=self._scan()["observed_at"]
        return before

    def trusted_exact_plan(self,candidate,rollback,scope,before)->bool:
        return (self.host_locked and self.freeze_locked
                and before==self.before
                and candidate==self.manifest["candidate_sha"]
                and rollback==self.manifest["rollback_sha"]
                and scope==self.manifest["source_scope_sha256"]
                and self.root_install_verified())

    def _signed_receipt(self)->dict[str,Any]:
        r=bootstrap.root_record(
            self.receipt_dir/("owner-"+self.approval_id+".json"),
            production=self.production)
        need(r.get("state")=="started"
             and r.get("component_id")==contract.COMPONENT
             and r.get("approval_id")==self.approval_id
             and r.get("candidate_sha")==self.manifest["candidate_sha"]
             and r.get("rollback_sha")==self.manifest["rollback_sha"]
             and r.get("scope_sha256")==self.manifest["source_scope_sha256"]
             and r.get("manifest_sha256")==digest(canonical(self.manifest))
             and r.get("freeze_sha256")==self.manifest["freeze_sha256"]
             and r.get("signed_owner_proof")==self.owner_proof,
             "NATIVE_STARTED_RECEIPT_NOT_BOUND")
        try:
            issued=datetime.fromisoformat(r["started_at"])
            key=(read_pinned_root_owner_public_key(OWNER_TRUST)
                 if self.production else self.code_test_public_key)
            proof=verify_exact_owner_release(
                self.owner_proof,public_key=key,
                expected_release_id="release-"+self.manifest["candidate_sha"][:16],
                expected_candidate_sha=self.manifest["candidate_sha"],
                expected_rollback_sha=self.manifest["rollback_sha"],
                expected_scope_sha256=self.manifest["source_scope_sha256"],
                expected_manifest_sha256=digest(canonical(self.manifest)),
                expected_freeze_sha256=self.manifest["freeze_sha256"],
                at=issued)
            need(proof["approval_id"]==self.approval_id,
                 "ORIGINAL_ONE_USE_OWNER_ID_CHANGED")
        except (KeyError,TypeError,ValueError,PermissionError) as exc:
            raise StageEHostDenied(
                "PMV4_E_NATIVE_HOST_SIGNED_RECEIPT_INVALID") from exc
        return r

    def native_started_receipt_verified(self,candidate,rollback,scope)->bool:
        self._verify_boundary()
        need((candidate,rollback,scope)==(
            self.manifest["candidate_sha"],self.manifest["rollback_sha"],
            self.manifest["source_scope_sha256"]),
            "SIGNED_RECEIPT_CALL_ARGUMENT_CHANGED")
        self._signed_receipt()
        return True

    def original_signed_started_receipt_verified(self,rollback,scope)->bool:
        return self.native_started_receipt_verified(
            self.manifest["candidate_sha"],rollback,scope)

    def reviewed_twelve_unit_hashes(self)->dict[str,str]:
        self._verify_boundary()
        files=bundle.generate(base=self.source_root)
        need(len(files)==12,"EXACT_TWELVE_REVIEWED_UNIT_FILES_MISSING")
        expected=self.scope["exact_replacement_files_sha256"]
        out={name:digest(body) for name,body in files.items()}
        need(all(expected.get(name)==hash for name,hash in out.items()),
             "SIGNED_REVIEWED_UNIT_SOURCE_CHANGED")
        self._approved_unit_hashes=out
        return out

    def persist_root_before_image(self,before:adapter.Before)->None:
        self._verify_boundary()
        self._signed_receipt()
        need(before==self.before and self._first_scan is not None,
             "BEFORE_IMAGE_NOT_THE_LIVE_MEASURED_BASELINE")
        self.code.prepare(
            candidate=self.manifest["candidate_sha"],scope=self.scope)
        sealed_dir(self.before_dir,production=self.production)
        child=self.before_dir/self.manifest["candidate_sha"]
        need(not child.exists() and not child.is_symlink(),
             "PHYSICAL_BEFORE_IMAGE_REPLAY")
        child.mkdir(mode=0o700)
        row={
            "schema_version":"1.0","action":packet.ACTION,
            "candidate_sha":self.manifest["candidate_sha"],
            "rollback_sha":self.manifest["rollback_sha"],
            "scope_sha256":self.manifest["source_scope_sha256"],
            "approval_id":self.approval_id,
            "ticket_scan_at":self._first_scan,
            "before":{
                **asdict(before),
                "active":sorted(before.active),
                "enabled":sorted(before.enabled),
            },
        }
        raw=packet.canonical(row)
        dest=child/"before.json"
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   getattr(os,"O_NOFOLLOW",0),0o400)
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        child.chmod(0o500)
        need(read_json(dest)==row,"PHYSICAL_BEFORE_READBACK_CHANGED")

    def _physical_before(self)->adapter.Before:
        dest=self.before_dir/self.manifest["candidate_sha"]/"before.json"
        row=read_json(dest)
        need(row.get("action")==packet.ACTION
             and row.get("candidate_sha")==self.manifest["candidate_sha"]
             and row.get("rollback_sha")==self.manifest["rollback_sha"]
             and row.get("scope_sha256")==self.manifest["source_scope_sha256"]
             and row.get("approval_id")==self.approval_id,
             "DURABLE_PHYSICAL_BEFORE_SCOPE_DRIFT")
        state=row.get("before")
        need(type(state) is dict and set(state)==set(adapter.Before.__dataclass_fields__),
             "DURABLE_PHYSICAL_BEFORE_SCHEMA_CHANGED")
        before=adapter.Before(
            active=frozenset(state["active"]),
            enabled=frozenset(state["enabled"]),
            policy_sha256=state["policy_sha256"],
            source_sha=state["source_sha"],
            freeze_sha256=state["freeze_sha256"],
            protected_fingerprint=state["protected_fingerprint"],
            claims_fingerprint=state["claims_fingerprint"],
            marker_present=state["marker_present"],
        )
        adapter.assert_exact_before(before)
        return before

    def verify_baseline(self,before:adapter.Before)->None:
        self._verify_boundary()
        need(before==self._physical_before()
             and not self._marker_present()
             and before.source_sha==self._source_revision()
             and before.protected_fingerprint==self._protected_hash(),
             "ORIGINAL_LIVE_BASELINE_DRIFT")

    def quiesce_and_verify_claims(self)->None:
        self._verify_boundary()
        self._ticket_owner()
        self._scan()
        # No modification of the Ticket Core lock or provider state.
        need(self.before is not None,
             "SIGNED_BEFORE_IMAGE_REQUIRED")

    def commit_reviewed_policy_and_code(self,candidate,rollback,scope)->None:
        self._verify_boundary()
        need(self.native_started_receipt_verified(candidate,rollback,scope),
             "NATIVE_STARTED_INVALID")
        self.code.apply(candidate=candidate,scope=self.scope)

    def verify_live_controlplane_alignment(self,candidate,rollback,scope)->bool:
        self._verify_boundary()
        need((candidate,rollback,scope)==(
            self.manifest["candidate_sha"],self.manifest["rollback_sha"],
            self.manifest["source_scope_sha256"]),
            "CONTROLPLANE_SOURCE_BINDING_CHANGED")
        witness=self.code.verify(candidate=candidate,scope=self.scope)
        need(witness["status"]=="native_reviewed_controlplane_bytes_installed"
             and witness["files"]==len(code.OBJECTS),
             "CONTROLPLANE_HOST_FILES_NOT_EXACT")
        return True

    def verify_six_callbacks_and_protected(self,before:adapter.Before)->None:
        self._verify_boundary()
        need(not self._marker_present()
             and self.systemd.verify_final(replacement=True)
             and self.verify_live_controlplane_alignment(
                 self.manifest["candidate_sha"],self.manifest["rollback_sha"],
                 self.manifest["source_scope_sha256"]),
             "SIX_LIVE_TRIGGER_PARITY_OR_CODE_CHANGED")
        need(self.freeze_and_protected_unchanged(before),
             "PROTECTED_RUNTIME_OR_FREEZE_CHANGED")
        # Source-only test callbacks return distinct samples immediately.
        # Production waits boundedly for a later *real* Ticket Core scan.
        end=time.monotonic()+(95 if self.production else 3)
        while True:
            scan=self._scan()
            if scan["observed_at"]!=self._first_scan:
                break
            need(time.monotonic()<end,"TICKET_SCAN_DID_NOT_ADVANCE")
            time.sleep(5 if self.production else 0.01)
        self._ticket_owner()
        self.parity_passed=True

    def _root_marker_record(self)->dict[str,Any]:
        before=self._physical_before()
        candidate=self.manifest["candidate_sha"]
        root_policy=code.read_exact(self.code.targets[code.POLICY])
        candidate_policy_sha=digest(root_policy)
        need(candidate_policy_sha!=before.policy_sha256
             and (not self.production or
                  before.policy_sha256==packet.EXPECTED_PRIOR_ROOT_POLICY),
             "POLICY_DELTA_NOT_EXACT")
        before_raw=code.read_exact(
            self.before_dir/candidate/"before.json")
        return {
            "schema_version":"1.0","action":packet.ACTION,
            "state":"accepted","source_sha":candidate,
            "owner_approval_id":self.approval_id,
            "source_scope_sha256":self.manifest["source_scope_sha256"],
            "source_rollback_sha":self.manifest["rollback_sha"],
            "prior_policy_sha256":packet.EXPECTED_PRIOR_ROOT_POLICY,
            "accepted_policy_sha256":candidate_policy_sha,
            "production_freeze_sha256":packet.EXPECTED_FREEZE,
            "replacement_user_units":sorted(adapter.NEW_USER),
            "replacement_system_units":sorted(adapter.NEW_ROOT),
            "retired_user_units":sorted(adapter.OLD_USER),
            "retired_system_units":sorted(adapter.OLD_ROOT),
            "watchdog_retargets_engineering":True,
            "root_reconcile_no_legacy_install":True,
            "root_parity_checks_passed":True,
            "native_drift":"pass",
            "accepted_at":datetime.now(timezone.utc).isoformat(),
            "rollback_receipt_sha256":digest(before_raw),
        }

    def commit_reviewed_root_marker(self,candidate,rollback,scope)->None:
        self._verify_boundary()
        need((candidate,rollback,scope)==(
            self.manifest["candidate_sha"],self.manifest["rollback_sha"],
            self.manifest["source_scope_sha256"]),
            "FINAL_MARKER_SCOPE_CHANGED")
        need(self.parity_passed
             and self.systemd.verify_final(replacement=True)
             and self.freeze_and_protected_unchanged(self._physical_before())
             and not self._marker_present(),
             "PARITY_NOT_ACCEPTED_BEFORE_MARKER")
        row=self._root_marker_record()
        # The parent must be public-readable for al-owned user-unit
        # ExecConditions to read the non-secret 0444 accepted marker.
        parent=self.marker.parent
        ancestor=parent.parent.lstat()
        need(not parent.parent.is_symlink()
             and ancestor.st_mode&0o022==0
             and (not self.production or
                  (ancestor.st_uid==0 and ancestor.st_gid==0)),
             "ROOT_OWNER_MARKER_ANCESTOR_UNTRUSTED")
        if not parent.exists():
            parent.mkdir(mode=0o755)
            # Secure root installers may set umask 077. Only this reviewed
            # non-secret acceptance folder needs 0755 so al-owned
            # ExecConditions can read the exact accepted marker.
            parent.chmod(0o755)
        info=parent.lstat()
        need(not parent.is_symlink()
             and (not self.production or
                  (info.st_uid==0 and info.st_gid==0))
             and stat.S_IMODE(info.st_mode)==0o755,
             "OWNER_MARKER_PARENT_MODE_CHANGED")
        fd=os.open(self.marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   getattr(os,"O_NOFOLLOW",0),0o444)
        with os.fdopen(fd,"wb") as stream:
            stream.write(packet.canonical(row));stream.flush();os.fsync(stream.fileno())
        # The root admission parser requires 0444, irrespective of the
        # operator's restrictive umask. Never weaken the parser.
        self.marker.chmod(0o444)
        verified=(admission.read_root_marker(self.marker)
                  if self.production else read_json(self.marker))
        need(verified==row,
             "ROOT_ACCEPTED_MARKER_READBACK_MISMATCH")

    def freeze_and_protected_unchanged(self,before:adapter.Before)->bool:
        try:
            return (before.protected_fingerprint==self._protected_hash()
                    and digest(code.read_exact(self.freeze))==
                        before.freeze_sha256)
        except (StageEHostDenied,PermissionError,OSError):
            return False

    def _step_record(self,step:str,*,recovery:bool)->None:
        self._verify_boundary()
        need(step in adapter.STEPS or step=="rollback_verified",
             "UNKNOWN_STEP_AUDIT")
        sealed_dir(self.step_dir,production=self.production)
        target=self.step_dir/(self.manifest["candidate_sha"]+".jsonl")
        seen=[]
        if target.exists() or target.is_symlink():
            info=target.lstat()
            need(not target.is_symlink() and stat.S_ISREG(info.st_mode)
                 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,
                 "STEP_AUDIT_FILE_UNTRUSTED")
            for line in target.read_bytes().splitlines():
                entry=json.loads(line)
                need(type(entry) is dict and set(entry)=={
                    "step","seq","previous_sha256","entry_sha256","recovery","at",
                },"STEP_AUDIT_SCHEMA_CHANGED")
                body={k:v for k,v in entry.items() if k!="entry_sha256"}
                need(entry["entry_sha256"]==digest(packet.canonical(body))
                     and entry["seq"]==len(seen)+1
                     and entry["previous_sha256"]==
                         (seen[-1]["entry_sha256"] if seen else "0"*64),
                     "STEP_AUDIT_CHAIN_DRIFT")
                seen.append(entry)
        value={
            "step":step,"seq":len(seen)+1,
            "previous_sha256":seen[-1]["entry_sha256"] if seen else "0"*64,
            "recovery":recovery,
            "at":datetime.now(timezone.utc).isoformat(),
        }
        entry={**value,"entry_sha256":digest(packet.canonical(value))}
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_APPEND|
                   getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"ab") as out:
            out.write(packet.canonical(entry)+b"\n")
            out.flush();os.fsync(out.fileno())

    def append_native_step_receipt(self,step,before)->None:
        need(before==self._physical_before(),
             "SIGNED_STEP_BEFORE_IMAGE_CHANGED")
        self._step_record(step,recovery=False)

    def read_immutable_root_before_image(self)->adapter.Before:
        self._verify_boundary()
        return self._physical_before()

    def block_new_dispatch(self)->None:
        # StageERootBridge immediately disables the six PMv4 triggers before
        # it can revoke the exact marker and restore old dispatch.
        self._verify_boundary()

    def revoke_exact_marker_before_legacy(self)->None:
        self._verify_boundary()
        if not self._marker_present():
            return
        record=(admission.read_root_marker(self.marker)
                if self.production else read_json(self.marker))
        need(record is not None
             and record["owner_approval_id"]==self.approval_id
             and record["source_sha"]==self.manifest["candidate_sha"]
             and record["source_scope_sha256"]==
                 self.manifest["source_scope_sha256"],
             "FOREIGN_ACCEPTED_MARKER_MUST_NOT_BE_REMOVED")
        self.marker.unlink()

    def restore_reviewed_policy_code_and_watchdog(self,before)->None:
        self._verify_boundary()
        need(before==self._physical_before() and not self._marker_present(),
             "EXACT_BEFORE_OR_MARKER_NOT_REVOKED")
        self.code.restore(
            candidate=self.manifest["candidate_sha"],scope=self.scope)
        self.parity_passed=False

    def restore_six_original_units_and_states(self,before)->None:
        self._verify_boundary()
        need(before==self._physical_before()
             and self.systemd.verify_final(replacement=False),
             "PHYSICAL_OLD_TRIGGER_RECOVERY_NOT_EXACT")

    def verify_rollback(self,before)->None:
        self._verify_boundary()
        need(before==self._physical_before()
             and self.systemd.verify_final(replacement=False)
             and not self._marker_present()
             and self.freeze_and_protected_unchanged(before),
             "SIGNED_NATIVE_RECOVERY_NOT_ACCEPTED")
        for name in code.OBJECTS:
            need(digest(code.read_exact(self.code.targets[name]))==
                 self.code.prior_sha256[name],
                 "ORIGINAL_CODE_BYTES_NOT_RESTORED")

    def append_native_recovery_receipt(self,before)->None:
        need(before==self._physical_before(),
             "RECOVERY_RECEIPT_BEFORE_CHANGED")
        self._step_record("rollback_verified",recovery=True)

    def observe_component(self,component_id:str)->str:
        """Physical native component identity; no fictitious Compose pointer.

        The original signed ledger observes its rollback source during the
        host-locked PREFLIGHT, before it takes the freeze lock. Observation is
        read-only; do not incorrectly require the later activation lock.
        """
        need(self.host_locked,"SIGNED_NATIVE_HOST_LOCK_REQUIRED")
        need(component_id==contract.COMPONENT,
             "OBSERVE_COMPONENT_SCOPE_UNREVIEWED")
        need(self._source_revision()==self.manifest["rollback_sha"],
             "PRESERVED_RUNTIME_BASELINE_CHANGED")
        if not self._marker_present():
            return self.manifest["rollback_sha"]
        marker=(admission.read_root_marker(self.marker)
                if self.production else read_json(self.marker))
        need(marker is not None
             and marker.get("source_sha")==self.manifest["candidate_sha"]
             and marker.get("source_rollback_sha")==self.manifest["rollback_sha"]
             and marker.get("source_scope_sha256")==
                 self.manifest["source_scope_sha256"]
             and marker.get("owner_approval_id")==self.approval_id
             and marker.get("state")=="accepted",
             "PHYSICAL_COMPONENT_MARKER_NOT_EXACT")
        return self.manifest["candidate_sha"]

    def verify_component(self,bundle:Path,
                         manifest:Mapping[str,Any])->bool:
        """Read back final installed state inside the original native ledger.

        After accepted-marker publication the signed code-switch guard
        intentionally cannot run again (it requires marker ABSENT). Verify
        exact candidate-vs-original file SHA from the earlier sealed root
        before-image directly, plus installed six trigger states, unique
        Ticket Core owner, untouched protected services and original freeze.
        """
        self._verify_boundary()
        need(type(manifest) is dict and manifest==self.manifest,
             "VERIFY_MANIFEST_NOT_SAME_SIGNED_RELEASE")
        need(isinstance(bundle,Path) and
             bundle.name in (self.manifest["candidate_sha"],
                             self.manifest["rollback_sha"]),
             "VERIFY_BUNDLE_ID_UNREVIEWED")
        before=self._physical_before()
        status=self.observe_component(contract.COMPONENT)
        candidate=bundle.name==self.manifest["candidate_sha"]
        need(status==bundle.name,"LIVE_COMPONENT_SOURCE_NOT_EXACT")
        need(self.systemd.verify_final(replacement=candidate),
             "LIVE_SYSTEMD_PARITY_MISMATCH")
        record,_=self.code._read_before(
            self.manifest["candidate_sha"],self.scope)
        expected=(record["candidate_sha256"]
                  if candidate else record["prior_sha256"])
        for name in code.OBJECTS:
            raw=code.read_exact(self.code.targets[name])
            identity=self.code.targets[name].lstat()
            need(digest(raw)==expected[name]
                 and (identity.st_uid,identity.st_gid,
                      stat.S_IMODE(identity.st_mode))==
                     self.code.identities[name],
                 "LIVE_CODE_OR_PROTECTED_POLICY_DRIFT")
        need(self.freeze_and_protected_unchanged(before),
             "PROTECTED_RUNTIME_OR_FREEZE_CHANGED")
        self._ticket_owner()
        self._scan()
        return True


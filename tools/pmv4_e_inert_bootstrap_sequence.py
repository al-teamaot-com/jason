#!/usr/bin/env python3
"""One exact signed Stage E inert root bootstrap sequence, no six-unit action.

The original native host/freezer and its independently verified Owner signature
must already be active. This library never issues approval, calls systemctl,
changes providers, restarts containers, or writes a final acceptance marker.
It connects existing root-only source staging, the signed BOOTSTRAP STARTED
journal, sealed Stage E trust installation, and original native release bundle.

An approved root-owned bootstrap entry must install this source, the already
reviewed dependencies and root journals before production construction.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any,Mapping

from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_signed_bootstrap_phase as signer
from tools import pmv4_e_native_root_manifest_attestation as attest
from tools.independent_component_release import _atomic_json

ENTRY=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_inert_bootstrap_sequence.py")
NATIVE_RELEASES=Path("/var/lib/jason/independent-component-release/releases")
TRUSTED_STAGE=Path("/opt/jason/pmv4-e-trusted")


class StageEBootstrapSequenceDenied(PermissionError):
    pass


def need(ok:bool,why:str)->None:
    if not ok:
        raise StageEBootstrapSequenceDenied("PMV4_E_BOOTSTRAP_SEQUENCE_"+why)


def canonical(raw:Mapping[str,Any])->bytes:
    return packet.canonical(dict(raw))


def root_dir(path:Path,*,production:bool,exact_mode:int)->None:
    try:info=path.lstat()
    except OSError as exc:
        raise StageEBootstrapSequenceDenied(
            "PMV4_E_BOOTSTRAP_SEQUENCE_PROTECTED_DIRECTORY_UNAVAILABLE") from exc
    need(not path.is_symlink()
         and stat.S_ISDIR(info.st_mode)
         and info.st_mode&0o022==0
         and stat.S_IMODE(info.st_mode)==exact_mode,
         "PROTECTED_DIRECTORY_NOT_SEALED")
    if production:
        need(info.st_uid==info.st_gid==0,
             "PROTECTED_DIRECTORY_NOT_ROOT_OWNED")


def trusted_json(path:Path,*,production:bool)->dict[str,Any]:
    meta=path.lstat()
    need(stat.S_ISREG(meta.st_mode) and not path.is_symlink()
         and meta.st_nlink==1
         and stat.S_IMODE(meta.st_mode)==0o444
         and (not production or meta.st_uid==meta.st_gid==0),
         "ROOT_RELEASE_RECORD_NOT_IMMUTABLE")
    try:x=json.loads(path.read_bytes())
    except (OSError,TypeError,ValueError) as exc:
        raise StageEBootstrapSequenceDenied(
            "PMV4_E_BOOTSTRAP_SEQUENCE_ROOT_RELEASE_RECORD_INVALID") from exc
    need(type(x) is dict,"ROOT_RELEASE_RECORD_NOT_OBJECT")
    return x


class InertBootstrapSequence:
    """Signed bootstrap and native root bundle; no owner or systemd authority."""

    def __init__(
        self,*,source_stager:Any,bootstrap:Any,
        trust_stager:Any,
        native_releases:Path=NATIVE_RELEASES,
        production:bool=True,
    ):
        if production:
            here=Path(__file__)
            meta=here.lstat()
            need(os.geteuid()==0
                 and here==ENTRY and here.resolve()==ENTRY
                 and not here.is_symlink()
                 and meta.st_uid==meta.st_gid==0
                 and stat.S_IMODE(meta.st_mode)==0o444
                 and native_releases==NATIVE_RELEASES,
                 "CANONICAL_ROOT_BOOTSTRAP_INSTALL_REQUIRED")
        # Original host+freeze lock checks and OWNER signature validation
        # are enforced by bootstrap.validate() and again by begin().
        self.source_stager=source_stager
        self.bootstrap=bootstrap
        self.trust_stager=trust_stager
        self.native_releases=Path(native_releases)
        self.production=production
        need(self.bootstrap.source_root==self.source_stager.source
             and self.trust_stager.target==TRUSTED_STAGE
             if production else True,
             "EXACT_SHARED_BOOTSTRAP_SOURCE_REQUIRED")

    def _persist_native_manifest(self,manifest:dict[str,Any],
                                 scope:dict[str,Any])->Path:
        root_dir(self.native_releases,production=self.production,
                 exact_mode=0o700)
        candidate=manifest["candidate_sha"]
        target=self.native_releases/candidate
        need(not target.exists() and not target.is_symlink(),
             "NATIVE_RELEASE_BUNDLE_CONFLICT")
        target.mkdir(mode=0o700)
        for name,value in (("manifest.json",manifest),
                           ("source-scope.json",scope)):
            raw=canonical(value)
            p=target/name
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as out:
                out.write(raw)
                out.flush();os.fsync(out.fileno())
            if self.production:os.chown(p,0,0)
            os.chmod(p,0o444)
        if self.production:os.chown(target,0,0)
        os.chmod(target,0o555)
        need({p.name for p in target.iterdir()}==
             {"manifest.json","source-scope.json"}
             and trusted_json(target/"manifest.json",
                              production=self.production)==manifest
             and trusted_json(target/"source-scope.json",
                              production=self.production)==scope,
             "NATIVE_RELEASE_BUNDLE_READBACK_FAILED")
        return target

    def prepare(self,request:Mapping[str,Any])->dict[str,Any]:
        """Use ONE authenticated exact Owner grant for inert source staging.

        Every production mutation requires the original root Owner
        signature, original host+freeze locks and live pre-cutover checks.
        On any crash, a partial root bundle is left inert for supervised
        exact recovery; no timer or provider is touched.
        """
        need(type(request) is dict,"SIGNED_REQUEST_NOT_A_DICT")
        candidate=request.get("candidate_sha")
        rollback=request.get("rollback_sha")
        reviewed=contract.draft(candidate_sha=candidate,
                                rollback_sha=rollback,
                                source_root=self.source_stager.source)
        manifest,scope=reviewed["manifest"],reviewed["source_scope"]
        first=self.bootstrap.validate(request)
        need(first["candidate_sha"]==candidate
             and first["manifest_sha256"]==reviewed["manifest_sha256"]
             and first["scope_sha256"]==manifest["source_scope_sha256"]
             and first["source_file_count"]==len(packet.REVIEWED_PATHS),
             "SOURCE_OWNER_PROOF_CHANGED")
        hashes=scope["exact_replacement_files_sha256"]
        source=self.source_stager.target_parent/candidate
        need(self.trust_stager.source==source,
             "STAGER_CANONICAL_SOURCE_CHANGED")
        need(not self.trust_stager.target.exists()
             and not self.trust_stager.target.is_symlink(),
             "STAGE_E_ROOT_ALREADY_STAGED")
        source_stage=self.source_stager.stage(candidate=candidate,
                                             exact_hashes=hashes)
        need(source_stage["status"]==
             "exact_immutable_candidate_source_staged_inert"
             and source_stage["source_file_count"]==len(hashes),
             "REVIEWED_ROOT_SOURCE_NOT_INSTALLED")
        # Independently revalidate every exact source file AGAIN from root
        # immutable candidate bytes before consuming one-use Owner approval.
        self.bootstrap.source_root=source
        started=self.bootstrap.begin(request)
        need(started["approval_id"]==first["approval_id"]
             and started["native_systemd_release_authorized"] is False,
             "SIGNED_INERT_STARTED_NOT_EXACT")
        root=self.trust_stager.stage(source_sha=candidate,
                                     exact_hashes=hashes)
        need(root["installed_file_count"]==len(hashes),
             "ROOT_TRUST_INVENTORY_NOT_EXACT")
        target=self._persist_native_manifest(manifest,scope)
        # The independent native attestor does not grant cutover authority.
        witness=attest.inspect(source_root=self.trust_stager.target,
                               release_dir=target,
                               production=self.production)
        need(witness["status"]==
             "root_source_attested_no_release_authority"
             and witness["candidate_sha"]==candidate
             and witness["scope_sha256"]==manifest["source_scope_sha256"]
             and witness["manifest_sha256"]==reviewed["manifest_sha256"]
             and witness["file_count"]==len(hashes)
             and witness["release_authorized"] is False,
             "INDEPENDENT_ROOT_ATTESTATION_DENIED")
        return {
            "status":"signed_owner_inert_stage_e_root_install_attested",
            "candidate_sha":candidate,
            "rollback_sha":rollback,
            "approval_id":first["approval_id"],
            "scope_sha256":manifest["source_scope_sha256"],
            "manifest_sha256":reviewed["manifest_sha256"],
            "reviewed_files":len(hashes),
            "root_authorization_to_retire":False,
            "legacy_systemd_changes":0,
            "provider_writes":0,
            "runtime_mcp_restarts":0,
        }

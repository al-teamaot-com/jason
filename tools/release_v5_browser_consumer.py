"""Dormant V5 Entra-admin signed browser decision host consumer.

Called ONLY from the existing release_mobile_approval_consumer after the
versioned root-owned policy changes from V4 to V5. This is not a second
Release Manager and cannot itself deploy, change freeze or grant authority.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.release_mobile_approval_consumer import (
    _private_atomic,_read_only_db,_read_active_owner_binding,
    _read_only_jason_identity,_protected_main_sha,
    MobileReleaseEvidenceBusy,_sqlite_busy,
)
from jason_runtime.release_v5_aot_policy import (
    CHANNEL,
)
from jason_runtime.release_v5_signed_evidence import (
    verify_browser_release_decision,public_key_fingerprint,_canonical,
)
from jason_runtime.release_v5_ca_attestation import (
    verify_root_ca_enforcement_receipt,
)
from jason_runtime.mobile_release_approval import (
    read_mobile_release_policy,read_eligible_release,
    read_release_approval_containment,create_mobile_release_request,
    digest,
)
from connectors.src.jason_connectors.approval_requests import (
    SQLiteApprovalRequestRepository,ApprovalRequestStatus,
)

_APPROVAL=re.compile(r"^relapproval-[0-9a-f]{32}$")


def _load_exact_root_public_key(path: Path,expected_sha: str) -> Ed25519PublicKey:
    try:
        info=path.lstat()
        raw=path.read_bytes()
    except (OSError,ValueError) as exc:
        raise PermissionError("V5_TRUSTED_ROOT_BROWSER_KEY_MISSING") from exc
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_uid not in {0,__import__("os").geteuid()}
            or info.st_gid not in {0,__import__("os").getegid()}
            or len(raw)!=32 or sha256(raw).hexdigest()!=expected_sha):
        raise PermissionError("V5_TRUSTED_ROOT_BROWSER_KEY_MISMATCH")
    return Ed25519PublicKey.from_public_bytes(raw)


def consume_v5_browser_release_decisions(
    *,repo:Path,state_root:Path,approve_release,record_initial_unfreeze,
    database:Path,policy_file:Path,ccc_root:Path,bindings_db:Path,
    authority_db:Path,protected_main_sha_reader=_protected_main_sha,
    public_key_path:Path|None=None,ca_attestation_path:Path|None=None,
    clock=lambda:datetime.now(timezone.utc),
) -> int:
    """Independently reverify original signed Entra decision before CCC+owner."""
    root=Path(state_root)
    policy=read_mobile_release_policy(policy_file)
    if policy.schema_version!="5.0" or policy.browser_policy is None:
        raise PermissionError("V5_SIGNED_BROWSER_POLICY_NOT_ENABLED")
    read_release_approval_containment(root).require_can_issue()
    key=_load_exact_root_public_key(
        public_key_path or root/"v5-owner-approval-public-key.raw",
        policy.browser_policy.signer_public_key_sha256,
    )
    try:
        db=_read_only_db(database)
        try:
            rows=db.execute("""
                SELECT a.approval_id,a.payload,r.response_json,
                       e.signed_envelope_json,e.evidence_sha256
                FROM approval_requests AS a
                INNER JOIN approval_decision_receipts AS r ON r.approval_id=a.approval_id
                INNER JOIN mobile_release_signed_evidence AS e ON e.approval_id=a.approval_id
                ORDER BY a.approval_id
            """).fetchall()
        finally:db.close()
    except __import__("sqlite3").OperationalError as exc:
        if _sqlite_busy(exc):
            raise MobileReleaseEvidenceBusy("V5 signed browser ledger is busy") from exc
        raise
    processed=root/"mobile-release-decisions-processed"
    count=0
    for aid,encoded,receipt_json,envelope_json,auth_sha in rows:
        if not isinstance(aid,str) or not _APPROVAL.fullmatch(aid):
            raise PermissionError("V5_SIGNED_BROWSER_APPROVAL_ID_INVALID")
        marker=processed/(aid+".json")
        if marker.is_file():
            previous=json.loads(marker.read_text(encoding="utf-8"))
            if (previous.get("approval_id")!=aid
                    or previous.get("signed_evidence_sha256")!=auth_sha):
                raise PermissionError("V5_SIGNED_BROWSER_PROCESSED_MARKER_CONFLICT")
            continue
        request=SQLiteApprovalRequestRepository._decode(encoded)
        receipt=json.loads(receipt_json)
        signed=json.loads(envelope_json)
        if (request.approval_id!=aid
                or request.status not in (
                    ApprovalRequestStatus.APPROVED,ApprovalRequestStatus.DENIED
                )
                or receipt.get("approval_id")!=aid
                or receipt.get("channel")!=CHANNEL
                or receipt.get("organization_id")!=policy.organization_id
                or receipt.get("approver_identity_id")!=policy.owner_identity_ids[0]
                or receipt.get("authentication_evidence_hash")!=auth_sha
                or not isinstance(receipt.get("channel_response_id"),str)
                or receipt["channel_response_id"]!=sha256(_canonical(signed)).hexdigest()):
            raise PermissionError("V5_BROWSER_DURABLE_RECEIPT_NOT_VERIFIED")
        moment=datetime.fromisoformat(receipt["decided_at"])
        if moment.tzinfo is None:
            raise PermissionError("V5_BROWSER_DECISION_TIMESTAMP_INVALID")
        proof=verify_browser_release_decision(
            signed=signed,request=request,policy=policy,public_key=key,
            now=clock(),
        )
        if (receipt.get("decision")!=proof["decision"]
                or auth_sha!=proof["auth_evidence_sha256"]
                or proof["decided_at"]!=receipt["decided_at"]):
            raise PermissionError("V5_SIGNED_BROWSER_EVIDENCE_RECEIPT_CHANGED")
        ca_sha=verify_root_ca_enforcement_receipt(
            ca_attestation_path or root/"v5-entra-ca-enforcement.json",
            browser_policy=policy.browser_policy,now=moment,
        )
        if ca_sha!=proof["ca_policy_receipt_sha256"]:
            raise PermissionError("V5_SIGNED_BROWSER_CA_POLICY_CHANGED")
        binding=_read_active_owner_binding(
            bindings_db,policy.browser_policy.tenant_id,
            policy.browser_policy.admin_approver_oid,
        )
        expected_id="person-entra-"+uuid.UUID(policy.browser_policy.admin_approver_oid).hex
        if (binding is None or binding.status!="active"
                or binding.microsoft_tenant_id!=policy.browser_policy.tenant_id
                or binding.microsoft_object_id!=policy.browser_policy.admin_approver_oid
                or binding.jason_identity_id!=expected_id
                or binding.client_id is not None):
            raise PermissionError("V5_ADMIN_OWNER_BINDING_NOT_ACTIVE")
        human=_read_only_jason_identity(authority_db,expected_id)
        if (human is None or human.identity_id!=expected_id
                or human.status!="active"
                or human.organization_id!=policy.organization_id
                or human.identity_type not in ("human","person")):
            raise PermissionError("V5_ADMIN_OWNER_IDENTITY_NOT_AUTHORIZED")
        evidence=read_eligible_release(
            root,request.metadata["release_id"],policy,
        )
        if (evidence.candidate_sha!=proof["candidate_sha"]
                or evidence.rollback_sha!=proof["rollback_sha"]
                or evidence.manifest_sha256!=proof["manifest_sha256"]
                or evidence.reviewed_scope_sha256!=proof["scope_sha256"]):
            raise PermissionError("V5_BROWSER_LIVE_RELEASE_DRIFT")
        expected=create_mobile_release_request(
            evidence,policy,now=request.requested_at,
        )
        if (request.metadata != {**expected.metadata,**{
                k:v for k,v in request.metadata.items()
                if k=="delivery_message_ids"}}
                or request.presentation!=expected.presentation
                or request.request_id!=expected.request_id
                or request.requested_mode!=expected.requested_mode
                or request.expires_at!=expected.expires_at):
            raise PermissionError("V5_BROWSER_RELEASE_OFFER_NO_LONGER_MATCHES")
        if protected_main_sha_reader(repo)!=evidence.candidate_sha:
            raise PermissionError("V5_BROWSER_CANDIDATE_NOT_PROTECTED_MAIN")
        read_release_approval_containment(root).require_request_eligible(
            request.requested_at,
        )
        if proof["decision"]=="deny":
            _private_atomic(marker,{
                "schema_version":"1.0","approval_id":aid,
                "signed_evidence_sha256":auth_sha,
                "release_id":evidence.release_id,
                "candidate_sha":evidence.candidate_sha,
                "decision":"deny","authority_mutated":False,
                "processed_at":clock().isoformat(),
            })
            count+=1
            continue
        record_path=root/"records"/(evidence.release_id+".json")
        record=json.loads(record_path.read_text(encoding="utf-8"))
        if ((record.get("owner_approval") or {}).get("approved") is True
                or record.get("state")!="production_eligible"):
            raise PermissionError("V5_BROWSER_RELEASE_ALREADY_HAS_OWNER_GRANT")
        name=ccc_root/("material-review-"+evidence.candidate_sha[:16]+".json")
        material={
            "schema_version":"1.0","status":"approved",
            "source_revision":evidence.candidate_sha,
            "recorded_by":policy.owner_identity_ids[0],
            "recorded_at":moment.astimezone(timezone.utc).isoformat(),
            "reason":"Authenticated Entra admin browser decision "+aid,
            "mobile_approval_id":aid,
            "signed_evidence_sha256":auth_sha,
            "release_manifest_sha256":evidence.manifest_sha256,
            "mobile_policy_sha256":policy.policy_sha256,
        }
        if name.exists():
            old=json.loads(name.read_text(encoding="utf-8"))
            if (old.get("source_revision")!=evidence.candidate_sha
                    or old.get("signed_evidence_sha256")!=auth_sha):
                archive=ccc_root/(
                    "material-review-"+evidence.candidate_sha[:16]
                    +"-previous-"+digest(old)[:12]+".json"
                )
                if not archive.exists():_private_atomic(archive,old)
        _private_atomic(name,material)
        _private_atomic(ccc_root/"material-review.json",material)
        read_release_approval_containment(root).require_request_eligible(
            request.requested_at,
        )
        approve_release(
            repo,root,release_id=evidence.release_id,
            candidate_sha=evidence.candidate_sha,
            source="authenticated_entra_browser_owner:"+aid,
        )
        if evidence.initial_freeze_binding is not None:
            if record_initial_unfreeze is None:
                raise PermissionError("V5_SIGNED_OWNER_UNFREEZE_FUNCTION_NOT_READY")
            record_initial_unfreeze(
                repo,root,release_id=evidence.release_id,
                candidate_sha=evidence.candidate_sha,
                approval_id=aid,
                signed_evidence_sha256=auth_sha,
                request_metadata=request.metadata,
                decided_at=moment,expires_at=request.expires_at,
            )
        _private_atomic(marker,{
            "schema_version":"1.0","approval_id":aid,
            "signed_evidence_sha256":auth_sha,
            "release_id":evidence.release_id,
            "candidate_sha":evidence.candidate_sha,
            "manifest_sha256":evidence.manifest_sha256,
            "mobile_policy_sha256":policy.policy_sha256,
            "decision":"approve","authority_mutated":True,
            "processed_at":clock().isoformat(),
        })
        count+=1
    return count

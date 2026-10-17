"""Host-side proof consumer for a single Teams-approved release + CCC review.

Called only by the existing release manager's governed promotion cycle.
No direct deploy, service restart, sudo, provider write or CCC PASS fabrication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
from typing import Callable

DEFAULT_MOBILE_DB = Path("/var/lib/jason/openclaw/mobile-release-approvals.sqlite3")
DEFAULT_POLICY = Path("/var/lib/jason/authority/mobile-release-approval-policy.json")
DEFAULT_CCC_ROOT = Path("/var/lib/jason/ccc")
DEFAULT_BINDINGS = Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")
DEFAULT_AUTHORITY = Path("/var/lib/jason/authority/authority.sqlite3")
DEFAULT_TRUSTED_KEYS = Path("/var/lib/jason/openclaw/trusted-keys/registry.json")


def _install_repo_modules(repo: Path) -> None:
    for path in (
        "implementation/runtime_service/src", "implementation/connectors/openclaw/src",
        "implementation", "implementation/mcp_service/src",
    ):
        root = str(repo / path)
        if root not in sys.path:
            sys.path.insert(0, root)


def _private_atomic(path: Path, doc: dict) -> None:
    """Write only 0600 regular files. Never follow a user-substituted symlink."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError("release/CCC evidence destination must be private regular file")
    fd, temp = tempfile.mkstemp(prefix=".mobile-release-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(doc, h, sort_keys=True, indent=2)
            h.write("\n")
            h.flush()
            os.fsync(h.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        dirfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def consume_mobile_release_decisions(
    *, repo: Path, state_root: Path,
    approve_release: Callable,
    database: Path = DEFAULT_MOBILE_DB,
    policy_file: Path = DEFAULT_POLICY,
    ccc_root: Path = DEFAULT_CCC_ROOT,
    bindings_db: Path = DEFAULT_BINDINGS,
    authority_db: Path = DEFAULT_AUTHORITY,
    trusted_keys: Path = DEFAULT_TRUSTED_KEYS,
) -> int:
    """Reauthenticate signed evidence, then record exact CCC and owner approval.

    The existing Release Manager still verifies GitHub main, candidate digest,
    protected baseline, preproduction, fresh CCC, rollback and operational
    health before any mutation. This is only the human authorization transfer.
    """
    if not database.is_file():
        return 0
    if not policy_file.is_file():
        # Feature disabled: do not consume stored approvals or block unrelated
        # manual releases. A missing owner policy never becomes an authorization.
        return 0
    _install_repo_modules(Path(repo))
    from connectors.src.jason_connectors.approval_requests import SQLiteApprovalRequestRepository
    from jason_runtime.mobile_release_approval import (
        CAPABILITY, REQUEST_PREFIX, create_mobile_release_request, digest,
        read_eligible_release, read_mobile_release_policy,
    )
    from jason_runtime.universal_teams_approval import SignedTeamsApprovalEvidenceVerifier
    from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry
    from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
    from kernel.identity_authority import SQLiteIdentityAuthorityStore, SQLiteIdentityRepository

    policy = read_mobile_release_policy(policy_file)
    con = sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True)
    try:
        records = con.execute("""
            SELECT a.approval_id, a.payload, r.response_json, e.signed_envelope_json,
                   e.evidence_sha256
              FROM approval_requests AS a
              INNER JOIN approval_decision_receipts AS r ON r.approval_id=a.approval_id
              INNER JOIN mobile_release_signed_evidence AS e ON e.approval_id=a.approval_id
             ORDER BY a.approval_id
        """).fetchall()
    finally:
        con.close()
    if not records:
        return 0
    key_auth = FileBackedTrustedKeyRegistry(trusted_keys).build_authenticator()
    bindings = SQLiteMicrosoftIdentityBindingStore(bindings_db)
    identities = SQLiteIdentityRepository(SQLiteIdentityAuthorityStore(authority_db))
    consumed_dir = state_root / "mobile-release-decisions-processed"
    completed = 0
    for approval_id, encoded, receipt_json, envelope_json, evidence_sha in records:
        if not isinstance(approval_id, str) or not approval_id.startswith(REQUEST_PREFIX):
            raise PermissionError("unknown mobile decision ID prefix")
        marker = consumed_dir / (approval_id + ".json")
        if marker.exists():
            stored = json.loads(marker.read_text(encoding="utf-8"))
            if stored.get("approval_id") != approval_id or stored.get("signed_evidence_sha256") != evidence_sha:
                raise PermissionError("processed mobile decision marker has conflicting evidence")
            continue
        request = SQLiteApprovalRequestRepository._decode(encoded)
        receipt = json.loads(receipt_json)
        if request.status.value != "approved":
            continue  # Deny does not create release authority.
        if (request.approval_id != approval_id
                or receipt.get("approval_id") != approval_id
                or receipt.get("decision") != "approve"
                or receipt.get("channel") != "microsoft_teams"
                or receipt.get("approver_identity_id") not in policy.owner_identity_ids
                or receipt.get("authentication_evidence_hash") != evidence_sha):
            raise PermissionError("durable mobile decision receipt is not owner-approved Teams evidence")
        timestamp = datetime.fromisoformat(receipt["decided_at"])
        if (timestamp.tzinfo is None or not (request.requested_at <= timestamp < request.expires_at)
                or request.organization_id != policy.organization_id
                or request.client_id is not None or request.requested_by != "svc-jason-release-manager"
                or request.capability != CAPABILITY
                or request.authorized_approver_ids != policy.owner_identity_ids
                or request.metadata.get("owner_policy_sha256") != policy.policy_sha256):
            raise PermissionError("mobile release decision was outside approved request and policy")
        signed = json.loads(envelope_json)
        verifier = SignedTeamsApprovalEvidenceVerifier(
            authenticator=key_auth, allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
            allowed_approval_prefixes=(REQUEST_PREFIX,), clock=lambda: timestamp,
        )
        token = json.dumps(signed, separators=(",", ":"), ensure_ascii=False)
        _, original = verifier.parse(token)
        principal = verifier.verify(token)
        submit = original.approval_submit
        if (submit is None or submit.approval_id != approval_id or submit.decision != "approve"
                or submit.channel_response_id != receipt.get("channel_response_id")
                or original.issued_at != timestamp or submit.selections
                or original.documents
                or principal.authentication_evidence_hash != evidence_sha):
            raise PermissionError("original signed Teams evidence does not match decision receipt")
        binding = bindings.find(microsoft_tenant_id=principal.tenant_id, microsoft_object_id=principal.object_id)
        if binding is None or binding.status != "active":
            raise PermissionError("mobile owner Entra binding has been revoked")
        owner = identities.get(binding.jason_identity_id)
        if (owner is None or owner.status != "active" or owner.organization_id != policy.organization_id
                or owner.identity_id != receipt["approver_identity_id"]
                or owner.identity_id == request.requested_by):
            raise PermissionError("mobile release approval has no active independent Jason owner identity")
        # Recovery is immutable: a crashed worker may have committed the
        # governed exact-owner approval before writing its processed marker.
        # Never redo or reuse it for another release; only restore bookkeeping
        # when the *same* source/manifest and signed CCC record prove success.
        release_id = request.metadata["release_id"]
        raw_release = json.loads((state_root / "records" / (release_id + ".json")).read_text())
        prior_approval = raw_release.get("owner_approval") or {}
        exact_prior_source = "authenticated_mobile_teams_owner:" + approval_id
        if prior_approval.get("approved") is True:
            manifest = raw_release.get("release_manifest") or {}
            named = ccc_root / ("material-review-" + request.metadata["candidate_sha"][:16] + ".json")
            if (prior_approval.get("source") != exact_prior_source
                    or prior_approval.get("candidate_sha") != request.metadata["candidate_sha"]
                    or digest(manifest) != request.metadata["manifest_sha256"]
                    or not named.is_file()):
                raise PermissionError("existing owner approval was not from this exact signed Teams decision")
            review = json.loads(named.read_text(encoding="utf-8"))
            if (review.get("source_revision") != request.metadata["candidate_sha"]
                    or review.get("recorded_by") != owner.identity_id
                    or review.get("signed_evidence_sha256") != evidence_sha
                    or review.get("mobile_approval_id") != approval_id):
                raise PermissionError("prior CCC review is not the same signed Teams decision")
            _private_atomic(marker, {
                "schema_version": "1.0", "approval_id": approval_id,
                "release_id": release_id, "candidate_sha": request.metadata["candidate_sha"],
                "manifest_sha256": request.metadata["manifest_sha256"],
                "mobile_policy_sha256": policy.policy_sha256,
                "signed_evidence_sha256": evidence_sha, "decision": "approve",
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "recovery": "previous_exact_owner_approval_verified",
            })
            continue
        candidate = read_eligible_release(state_root, release_id, policy)
        expected = create_mobile_release_request(candidate, policy, now=request.requested_at)
        if (request.metadata != {**expected.metadata, **{
                key: value for key, value in request.metadata.items()
                if key == "delivery_message_ids"}}
                or request.presentation != expected.presentation
                or request.expires_at != expected.expires_at
                or request.requested_mode != expected.requested_mode):
            raise PermissionError("mobile release policy or exact reviewed manifest changed")

        # All trusted evidence is now independently reverified. CCC is an
        # *owner material review*, not a CCC PASS; fresh CCC must still run.
        sha = candidate.candidate_sha
        material_review = {
            "schema_version": "1.0", "status": "approved", "source_revision": sha,
            "recorded_by": owner.identity_id,
            "recorded_at": timestamp.astimezone(timezone.utc).isoformat(),
            "reason": "Authenticated Teams owner decision " + approval_id,
            "mobile_approval_id": approval_id,
            "signed_evidence_sha256": evidence_sha,
            "release_manifest_sha256": candidate.manifest_sha256,
            "mobile_policy_sha256": policy.policy_sha256,
        }
        named = ccc_root / ("material-review-" + sha[:16] + ".json")
        if named.exists():
            prior = json.loads(named.read_text(encoding="utf-8"))
            if prior.get("source_revision") != sha or prior.get("recorded_by") != owner.identity_id:
                raise PermissionError("conflicting CCC owner review for exact SHA")
            if prior.get("signed_evidence_sha256") != evidence_sha:
                # An older manual owner review is valid provenance, but it is
                # not the signed mobile receipt. Archive it without deletion
                # and preserve the newly authorized signed per-SHA review.
                archived = ccc_root / (
                    "material-review-" + sha[:16] + "-previous-" + digest(prior)[:12] + ".json"
                )
                if not archived.exists():
                    _private_atomic(archived, prior)
                _private_atomic(named, material_review)
        else:
            _private_atomic(named, material_review)
        current = ccc_root / "material-review.json"
        if current.exists():
            old = json.loads(current.read_text(encoding="utf-8"))
            if old.get("source_revision") != sha:
                # A new authenticated exact-SHA decision allows replacing the
                # canonical pointer; keep the old named review as audit evidence.
                previous = str(old.get("source_revision") or "")
                if not re_full_sha(previous):
                    raise PermissionError("existing CCC owner review has invalid revision")
                prior_named = ccc_root / ("material-review-" + previous[:16] + ".json")
                if not prior_named.exists():
                    _private_atomic(prior_named, old)
        _private_atomic(current, material_review)

        # Exact released artifacts and protected main are verified by existing
        # approve_release; this call never starts production itself.
        approve_release(
            repo, state_root, release_id=candidate.release_id,
            candidate_sha=sha, source="authenticated_mobile_teams_owner:" + approval_id,
        )
        _private_atomic(marker, {
            "schema_version": "1.0", "approval_id": approval_id,
            "release_id": candidate.release_id,
            "candidate_sha": sha,
            "manifest_sha256": candidate.manifest_sha256,
            "mobile_policy_sha256": policy.policy_sha256,
            "signed_evidence_sha256": evidence_sha,
            "decision": "approve",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        completed += 1
    return completed


def re_full_sha(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{40}", value) is not None

"""Host-side proof consumer for a single Teams-approved release + CCC review.

Called only by the existing release manager's governed promotion cycle.
No direct deploy, service restart, sudo, provider write or CCC PASS fabrication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import uuid
from typing import Callable
from urllib.parse import quote

DEFAULT_MOBILE_DB = Path("/var/lib/jason/openclaw/mobile-release-approvals.sqlite3")
DEFAULT_POLICY = Path("/var/lib/jason/authority/mobile-release-approval-policy.json")
DEFAULT_CCC_ROOT = Path("/var/lib/jason/ccc")
DEFAULT_BINDINGS = Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")
DEFAULT_AUTHORITY = Path("/var/lib/jason/authority/authority.sqlite3")
DEFAULT_TRUSTED_KEYS = Path("/var/lib/jason/openclaw/trusted-keys/registry.json")
OWNER_EMAIL_FALLBACKS = {"person-al": "al@teamaot.com"}


class MobileReleaseEvidenceBusy(RuntimeError):
    """Transient SQLITE_BUSY/LOCKED while reading independent owner evidence."""


def _sqlite_busy(error: sqlite3.OperationalError) -> bool:
    return getattr(error, "sqlite_errorcode", None) in {
        sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED,
    }


def _read_only_db(path: Path) -> sqlite3.Connection:
    # URI read-only mode never initializes schemas, migrates tables, modifies
    # permission bits, or requests a write lock on live authority state.
    encoded = quote(str(Path(path).absolute()), safe="/")
    return sqlite3.connect("file:" + encoded + "?mode=ro", uri=True, timeout=1.0)


def _read_active_owner_binding(path: Path, tenant_id: str, object_id: str):
    from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
    try:
        connection = _read_only_db(path)
        try:
            row = connection.execute(
                """SELECT microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                          client_id, email_address, status
                     FROM microsoft_identity_bindings
                    WHERE microsoft_tenant_id = ? AND microsoft_object_id = ?""",
                (tenant_id, object_id),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.OperationalError as exc:
        if _sqlite_busy(exc):
            raise MobileReleaseEvidenceBusy("owner binding evidence database busy") from exc
        raise
    return None if row is None else SQLiteMicrosoftIdentityBindingStore._from_row(row)


def _read_only_jason_identity(path: Path, identity_id: str):
    from kernel.identity_authority import IdentityRecord
    try:
        connection = _read_only_db(path)
        try:
            row = connection.execute(
                "SELECT payload FROM identities WHERE identity_id=?",
                (identity_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.OperationalError as exc:
        if _sqlite_busy(exc):
            raise MobileReleaseEvidenceBusy("owner identity evidence database busy") from exc
        raise
    return None if row is None else IdentityRecord(**json.loads(row[0]))


def _authorized_policy_owner_identity(*, binding, owner, policy, receipt_identity_id: str) -> str:
    """Resolve one authenticated Entra actor to the already-authorized policy owner.

    The release policy remains symbolic (person-al). A canonical Entra-derived
    Jason identity may satisfy that symbolic owner only when the active binding
    proves the exact reviewed Owner email, object-derived identity, AOT scope,
    and no client scope. This mirrors the runtime delivery/callback boundary
    without adding a new approver.
    """
    if receipt_identity_id not in policy.owner_identity_ids:
        raise PermissionError("mobile release receipt approver is outside owner policy")
    if (owner is None or owner.status != "active"
            or owner.organization_id != policy.organization_id):
        raise PermissionError("mobile release approval has no active independent Jason owner identity")
    if owner.identity_id == receipt_identity_id:
        return receipt_identity_id
    fallback_email = OWNER_EMAIL_FALLBACKS.get(receipt_identity_id)
    if fallback_email is None:
        raise PermissionError("mobile release approval has no active independent Jason owner identity")
    try:
        expected_identity = (
            "person-entra-" + uuid.UUID(str(binding.microsoft_object_id)).hex
        )
    except (ValueError, AttributeError, TypeError) as exc:
        raise PermissionError("mobile release owner binding identity is invalid") from exc
    if (
        str(getattr(binding, "email_address", "") or "").strip().casefold()
        != fallback_email.casefold()
        or getattr(binding, "client_id", None) is not None
        or str(getattr(binding, "jason_identity_id", "")) != expected_identity
        or str(getattr(owner, "identity_id", "")) != expected_identity
    ):
        raise PermissionError("mobile release approval has no active independent Jason owner identity")
    return receipt_identity_id


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
        read_explicit_release_renewal,
    )
    from jason_runtime.universal_teams_approval import SignedTeamsApprovalEvidenceVerifier
    from jason_runtime.owner_release_approval_containment import read_release_approval_containment
    from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry

    policy = read_mobile_release_policy(policy_file)
    containment = read_release_approval_containment(state_root)
    if containment.active:
        print('OWNER_RELEASE_APPROVAL_HOLD_ACTIVE=' + containment.hold_id, flush=True)
        return 0  # Do not convert held Teams decisions into owner/CCC authority.
    try:
        con = _read_only_db(database)
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
    except sqlite3.OperationalError as exc:
        if _sqlite_busy(exc):
            raise MobileReleaseEvidenceBusy("signed owner decision ledger busy") from exc
        raise
    if not records:
        return 0

    consumed_dir = state_root / "mobile-release-decisions-processed"

    def already_processed(approval_id: str, evidence_sha: str) -> bool:
        marker = consumed_dir / (approval_id + ".json")
        if not marker.exists():
            return False
        stored = json.loads(marker.read_text(encoding="utf-8"))
        if (stored.get("approval_id") != approval_id
                or stored.get("signed_evidence_sha256") != evidence_sha):
            raise PermissionError("processed mobile decision marker has conflicting evidence")
        return True

    def processed_marker_needs_exact_reconstruction(
        approval_id: str, evidence_sha: str,
    ) -> bool:
        """Return True only when an exact processed grant lost record materialization.

        This is not decision replay. The immutable processed marker merely makes
        the original signed receipt eligible for full re-verification below when
        the same production-eligible release record has been recreated without
        its owner_approval field. Candidate SHA and manifest digest must still
        match exactly. Changed, historical or completed releases stay processed.
        """
        marker = consumed_dir / (approval_id + ".json")
        if not marker.exists():
            return False
        stored = json.loads(marker.read_text(encoding="utf-8"))
        if (stored.get("approval_id") != approval_id
                or stored.get("signed_evidence_sha256") != evidence_sha):
            raise PermissionError("processed mobile decision marker has conflicting evidence")
        if stored.get("decision") != "approve" or stored.get("review_only") is True:
            return False
        release_id = str(stored.get("release_id") or "")
        candidate_sha = str(stored.get("candidate_sha") or "")
        manifest_sha = str(stored.get("manifest_sha256") or "")
        if (not release_id or not re_full_sha(candidate_sha)
                or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha)):
            raise PermissionError("processed mobile decision marker is incomplete")
        record_path = state_root / "records" / (release_id + ".json")
        if not record_path.is_file():
            return False
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if (record.get("state") != "production_eligible"
                or str((record.get("release_candidate") or {}).get("candidate_sha") or "")
                    != candidate_sha
                or digest(record.get("release_manifest") or {}) != manifest_sha):
            return False
        # Missing approval alone is not evidence of lost materialization: unit
        # tests and alternative exact approvers may intentionally leave release
        # persistence to the caller. Reconstruction is eligible only when the
        # current release record itself proves it was recreated *after* this
        # immutable Teams decision had already been processed.
        try:
            marker_processed_at = datetime.fromisoformat(str(stored["processed_at"]))
            record_created_at = datetime.fromisoformat(str(record["created_at"]))
        except (KeyError, TypeError, ValueError):
            return False
        if (marker_processed_at.tzinfo is None or record_created_at.tzinfo is None
                or record_created_at <= marker_processed_at):
            return False
        approval = record.get("owner_approval") or {}
        if approval.get("approved") is True:
            exact_source = "authenticated_mobile_teams_owner:" + approval_id
            if (approval.get("candidate_sha") != candidate_sha
                    or approval.get("source") != exact_source):
                raise PermissionError(
                    "processed Teams decision conflicts with current owner approval"
                )
            return False
        return True

    # A completed historical decision needs no authority-database read at all.
    # Validate every immutable receipt marker BEFORE loading identity stores.
    # This eliminates schema write-lock attempts on 1.8 GiB of shared authority
    # data every five minutes when nothing is pending.
    pending = []
    for row in records:
        approval_id, _, _, _, evidence_sha = row
        if not isinstance(approval_id, str) or not approval_id.startswith(REQUEST_PREFIX):
            raise PermissionError("unknown mobile decision ID prefix")
        if (not already_processed(approval_id, evidence_sha)
                or processed_marker_needs_exact_reconstruction(
                    approval_id, evidence_sha
                )):
            pending.append(row)
    if not pending:
        return 0

    key_auth = FileBackedTrustedKeyRegistry(trusted_keys).build_authenticator()
    completed = 0
    for approval_id, encoded, receipt_json, envelope_json, evidence_sha in pending:
        # Another authenticated cycle may have just completed this receipt.
        reconstructing_processed = processed_marker_needs_exact_reconstruction(
            approval_id, evidence_sha
        )
        if already_processed(approval_id, evidence_sha) and not reconstructing_processed:
            continue
        marker = consumed_dir / (approval_id + ".json")
        request = SQLiteApprovalRequestRepository._decode(encoded)
        if not containment.is_request_eligible(request.requested_at):
            # Immutable revocation watermark survives release of the hold.
            # Preserve historical receipt/evidence, but never materialize it.
            continue
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
            allowed_selection_keys=(frozenset({"card_challenge"})
                                    if policy.schema_version == "2.0" else frozenset()),
        )
        token = json.dumps(signed, separators=(",", ":"), ensure_ascii=False)
        _, original = verifier.parse(token)
        principal = verifier.verify(token)
        submit = original.approval_submit
        if (submit is None or submit.approval_id != approval_id or submit.decision != "approve"
                or submit.channel_response_id != receipt.get("channel_response_id")
                or original.issued_at != timestamp
                or original.documents
                or principal.authentication_evidence_hash != evidence_sha):
            raise PermissionError("original signed Teams evidence does not match decision receipt")
        if policy.schema_version == "2.0":
            proof = request.metadata.get("card_instance_challenge")
            if (type(proof) is not str or re.fullmatch(r"[0-9a-f]{48}", proof) is None
                    or hashlib.sha256(proof.encode("ascii")).hexdigest()
                        != request.metadata.get("card_instance_challenge_sha256")
                    or dict(submit.selections) != {"card_challenge": proof}):
                raise PermissionError("host attestation lacks original card-instance proof")
        elif submit.selections:
            raise PermissionError("legacy signed release cannot contain card changes")
        binding = _read_active_owner_binding(
            bindings_db, principal.tenant_id, principal.object_id
        )
        if binding is None or binding.status != "active":
            raise PermissionError("mobile owner Entra binding has been revoked")
        owner = _read_only_jason_identity(authority_db, binding.jason_identity_id)
        policy_owner_identity = _authorized_policy_owner_identity(
            binding=binding,
            owner=owner,
            policy=policy,
            receipt_identity_id=str(receipt["approver_identity_id"]),
        )
        if (owner.identity_id == request.requested_by
                or policy_owner_identity == request.requested_by):
            raise PermissionError("mobile release approval has no active independent Jason owner identity")
        # Recovery is immutable: a crashed worker may have committed the
        # governed exact-owner approval before writing its processed marker.
        # Never redo or reuse it for another release; only restore bookkeeping
        # when the *same* source/manifest and signed CCC record prove success.
        release_id = request.metadata["release_id"]
        raw_release = json.loads((state_root / "records" / (release_id + ".json")).read_text())
        prior_approval = raw_release.get("owner_approval") or {}
        exact_prior_source = "authenticated_mobile_teams_owner:" + approval_id
        read_release_approval_containment(state_root).require_request_eligible(
            request.requested_at
        )
        review_only = request.metadata.get("review_only") is True
        if review_only:
            if (policy.schema_version != "2.0"
                    or prior_approval.get("approved") is not True
                    or prior_approval.get("candidate_sha") != request.metadata.get("candidate_sha")
                    or digest(raw_release.get("release_manifest") or {})
                        != request.metadata.get("manifest_sha256")):
                raise PermissionError("CCC-only Teams decision lacks an exact prior owner release grant")
        if prior_approval.get("approved") is True and not review_only:
            manifest = raw_release.get("release_manifest") or {}
            named = ccc_root / ("material-review-" + request.metadata["candidate_sha"][:16] + ".json")
            if (prior_approval.get("source") != exact_prior_source
                    or prior_approval.get("candidate_sha") != request.metadata["candidate_sha"]
                    or digest(manifest) != request.metadata["manifest_sha256"]
                    or not named.is_file()):
                raise PermissionError("existing owner approval was not from this exact signed Teams decision")
            review = json.loads(named.read_text(encoding="utf-8"))
            if (review.get("source_revision") != request.metadata["candidate_sha"]
                    or review.get("recorded_by") != policy_owner_identity
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
        candidate = read_eligible_release(
            state_root, release_id, policy,
            allow_existing_owner_approval=review_only,
        )
        if candidate.review_only != review_only:
            raise PermissionError("CCC-only Teams decision changed release approval state")
        renewal_nonce = request.metadata.get("renewal_nonce")
        renewed_from = request.metadata.get("renewed_from_approval_id")
        if renewal_nonce is not None or renewed_from is not None:
            if renewal_nonce is None or renewed_from is None:
                raise PermissionError("host sees incomplete signed renewal lineage")
            # Read-only independent SQLite evidence, not the callback's authority.
            connection = _read_only_db(database)
            try:
                class ParentReadPort:
                    def get(self, approval_id):
                        row = connection.execute(
                            "SELECT payload FROM approval_requests WHERE approval_id=?",
                            (approval_id,),
                        ).fetchone()
                        return (None if row is None
                                else SQLiteApprovalRequestRepository._decode(row[0]))

                    def accepted_decision(self, approval_id):
                        return connection.execute(
                            "SELECT 1 FROM approval_decision_receipts WHERE approval_id=?",
                            (approval_id,),
                        ).fetchone()

                verified_parent = read_explicit_release_renewal(
                    state_root, ParentReadPort(), candidate, policy,
                    renewal_nonce, requested_at=request.requested_at,
                )
            finally:
                connection.close()
            if verified_parent != renewed_from:
                raise PermissionError("signed renewed release parent evidence mismatched")
        expected = create_mobile_release_request(
            candidate, policy, now=request.requested_at,
            card_challenge=(request.metadata.get("card_instance_challenge")
                            if policy.schema_version == "2.0" else None),
            renewed_from=renewed_from, renewal_nonce=renewal_nonce,
        )
        if (request.metadata != {**expected.metadata, **{
                key: value for key, value in request.metadata.items()
                if key == "delivery_message_ids"}}
                or request.presentation != expected.presentation
                or request.expires_at != expected.expires_at
                or request.requested_mode != expected.requested_mode
                or request.request_id != expected.request_id
                or request.correlation_id != expected.correlation_id):
            raise PermissionError("mobile release policy or exact reviewed manifest changed")

        # Cross-process race guard immediately before CCC/release state writes.
        # A hold activated while evidence was being verified must still win.
        read_release_approval_containment(state_root).require_request_eligible(
            request.requested_at
        )
        # Revalidate the existing owner authorization immediately before
        # writing a CCC-only review; the signed card cannot resurrect or alter
        # a grant revoked after the original Teams callback.
        if review_only:
            just_before = json.loads(
                (state_root / "records" / (release_id + ".json")).read_text()
            )
            if (just_before.get("owner_approval") != prior_approval
                    or digest(just_before.get("release_manifest") or {})
                        != candidate.manifest_sha256
                    or just_before.get("state") != "production_eligible"):
                raise PermissionError("exact prior owner release grant changed before CCC write")
        # All trusted evidence is now independently reverified. CCC is an
        # *owner material review*, not a CCC PASS; fresh CCC must still run.
        sha = candidate.candidate_sha
        material_review = {
            "schema_version": "1.0", "status": "approved", "source_revision": sha,
            "recorded_by": policy_owner_identity,
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
            if prior.get("source_revision") != sha or prior.get("recorded_by") != policy_owner_identity:
                raise PermissionError("conflicting CCC owner review for exact SHA")
            if review_only and (prior.get("signed_evidence_sha256") != evidence_sha
                                or prior.get("mobile_approval_id") != approval_id):
                raise PermissionError("CCC-only Teams review conflicts with an existing owner review")
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
        # Check one final time before transferring authority to the existing
        # exact-SHA release approver. Card delivery/CCC files are not sufficient.
        read_release_approval_containment(state_root).require_request_eligible(
            request.requested_at
        )
        if not review_only:
            approve_release(
                repo, state_root, release_id=candidate.release_id,
                candidate_sha=sha, source="authenticated_mobile_teams_owner:" + approval_id,
            )
        else:
            # Only the existing owner release grant is valid. A signed CCC
            # review cannot add, modify or resurrect release execution scope.
            stored = json.loads((state_root / "records" / (release_id + ".json")).read_text())
            if stored.get("owner_approval") != prior_approval:
                raise PermissionError("prior exact owner release grant changed during CCC review")
        if not reconstructing_processed:
            _private_atomic(marker, {
                "schema_version": "1.0", "approval_id": approval_id,
                "release_id": candidate.release_id,
                "candidate_sha": sha,
                "manifest_sha256": candidate.manifest_sha256,
                "mobile_policy_sha256": policy.policy_sha256,
                "signed_evidence_sha256": evidence_sha,
                "decision": "approve",
                **({"review_only": True} if review_only else {}),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            })
        completed += 1
    return completed


def re_full_sha(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{40}", value) is not None

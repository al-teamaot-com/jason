"""Owner-only mobile release + CCC approval, disabled until separately activated.

The Teams gateway carries a signed button decision, not release authority.
The immutable release-manifest fingerprint and local owner policy bind the
request. A separate host consumer must validate durable decision evidence
before creating CCC/release approval artifacts; the HTTP handler never deploys.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from typing import Any, Mapping

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision, ApprovalPresentation, ApprovalRequest,
    ApprovalRequestService, ApprovalRequestStatus, ApprovalResponse,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from jason_runtime.owner_release_approval_containment import read_release_approval_containment

SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID = re.compile(r"^release-[0-9a-f]{16}$")
CAPABILITY = "release.production.approve"
REQUEST_PREFIX = "relapproval-"
RISK_LEVELS = frozenset({"normal", "production_repair", "production_control_core", "schema_or_contract"})
_LOG = logging.getLogger(__name__)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class MobileReleasePolicy:
    organization_id: str
    owner_identity_ids: tuple[str, ...]
    allowed_risk_profiles: frozenset[str]
    ttl_seconds: int
    policy_sha256: str
    schema_version: str = "1.0"


def read_mobile_release_policy(path: Path) -> MobileReleasePolicy:
    """A separately approved, private owner policy; absent/malformed fails closed."""
    p = Path(path)
    info = p.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid not in (0, os.geteuid())):
        raise PermissionError("mobile release policy must be owned 0600 regular file")
    raw = p.read_bytes()
    if len(raw) > 8192:
        raise PermissionError("mobile release policy too large")
    doc = json.loads(raw)
    shared = {"schema_version", "organization_id", "policy_mode", "owner_identity_ids",
              "allowed_risk_profiles", "ttl_seconds", "capability"}
    # V1 remains *exactly* the approved normal-risk pilot. V2 is opt-in through
    # a separate 0600 Owner-reviewed policy and an explicit runtime mode.
    # A mere source deployment or updated allowed_risk_profiles cannot turn
    # the already-running V1 pilot into protected release authority.
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version == "1.0":
        expected = shared
        mode = "owner_only_pilot"
    elif version == "2.0":
        expected = shared | {"high_impact_review"}
        mode = "owner_reviewed"
    else:
        raise PermissionError("unsupported versioned mobile release policy")
    if (set(doc) != expected
            or doc["organization_id"] != "aot"
            or doc["policy_mode"] != mode
            or doc["capability"] != CAPABILITY
            or doc["owner_identity_ids"] != ["person-al"]):
        raise PermissionError("mobile release policy role, version or mode is not authorized")
    risks = doc["allowed_risk_profiles"]
    ttl = doc["ttl_seconds"]
    if (not isinstance(risks, list) or not risks or len(set(risks)) != len(risks)
            or any(not isinstance(risk, str) or risk not in RISK_LEVELS for risk in risks)
            or type(ttl) is not int or not 300 <= ttl <= (1800 if version == "1.0" else 900)):
        raise PermissionError("mobile release policy risk or TTL is invalid")
    if version == "1.0":
        if set(risks) != {"normal"}:
            raise PermissionError("owner-only mobile pilot is limited to normal-risk releases")
    else:
        review = doc["high_impact_review"]
        if (not isinstance(review, dict)
                or review != {
                    "owner_exact_sha_required": True,
                    "signed_teams_identity_required": True,
                    "independent_ccc_required": True,
                    "protected_release_gates_unchanged": True,
                } or "normal" not in risks):
            raise PermissionError("high-impact Teams release policy requires explicit reviewed controls")
        # A V2 policy authorizes *the channel*, never a class-wide standing
        # release grant. Each approval remains a one-time, signed owner vote
        # for a single immutable release and manifest; root gates still run.
    return MobileReleasePolicy(
        "aot", ("person-al",), frozenset(risks), ttl, digest(doc), version,
    )


@dataclass(frozen=True, slots=True)
class ExactRelease:
    release_id: str
    candidate_sha: str
    rollback_sha: str
    manifest_sha256: str
    policy_sha256: str
    desired_state_policy_digest: str
    risk_profile: str
    change_class: str
    purpose: str
    affected_files: tuple[str, ...]
    affected_surfaces: tuple[str, ...]


def read_eligible_release(state_root: Path, release_id: str, policy: MobileReleasePolicy) -> ExactRelease:
    if not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id):
        raise ValueError("release ID must be exact")
    p = Path(state_root) / "records" / (release_id + ".json")
    info = p.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise PermissionError("release record must not be writable by group/other or a link")
    doc = json.loads(p.read_text(encoding="utf-8"))
    candidate = doc.get("release_candidate")
    manifest = doc.get("release_manifest")
    preprod = doc.get("preproduction")
    if (doc.get("release_id") != release_id or doc.get("state") != "production_eligible"
            or not isinstance(candidate, dict) or not isinstance(manifest, dict)
            or not isinstance(preprod, dict) or preprod.get("acceptance_passed") is not True
            or preprod.get("rollback_readiness_passed") is not True
            or preprod.get("provider_mutations_disabled") is not True
            or (doc.get("owner_approval") or {}).get("approved") is True):
        raise PermissionError("release is not pending owner approval with safe preproduction evidence")
    sha = candidate.get("candidate_sha")
    rollback = doc.get("rollback_sha")
    if (not isinstance(sha, str) or not SHA.fullmatch(sha)
            or not isinstance(rollback, str) or not SHA.fullmatch(rollback)
            or release_id != "release-" + sha[:16]
            or manifest.get("candidate_sha") != sha or manifest.get("rollback_sha") != rollback
            or preprod.get("deployed_sha") != sha
            or candidate.get("artifact_digest") != preprod.get("artifact_digest")
            or candidate.get("mcp_artifact_digest") != preprod.get("mcp_artifact_digest")):
        raise PermissionError("release candidate identity or immutable image digests changed")
    risk = doc.get("risk_profile")
    if (risk not in policy.allowed_risk_profiles or manifest.get("risk_profile") != risk
            or manifest.get("risk_profile") not in RISK_LEVELS):
        raise PermissionError("release exceeds owner-only mobile approval risk profile")
    files = manifest.get("changed_files")
    surfaces = manifest.get("surfaces")
    if (not isinstance(files, list) or not all(isinstance(f, str) and f for f in files)
            or not isinstance(surfaces, list) or not all(isinstance(f, str) and f for f in surfaces)):
        raise PermissionError("release manifest has no reviewable bounded change inventory")
    purpose = doc.get("description")
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 500:
        raise PermissionError("mobile release card must contain a bounded human-readable change purpose")
    return ExactRelease(release_id, sha, rollback, digest(manifest),
        str(manifest.get("policy_digest") or ""),
        str(manifest.get("desired_state_policy_digest") or ""),
        risk, str(manifest.get("change_class") or ""), purpose.strip(),
        tuple(files), tuple(surfaces))


def create_mobile_release_request(evidence: ExactRelease, policy: MobileReleasePolicy,
                                  *, now: datetime | None = None,
                                  card_challenge: str | None = None) -> ApprovalRequest:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("mobile approval clock must be timezone-aware")
    if evidence.risk_profile not in policy.allowed_risk_profiles:
        raise PermissionError("release risk is not authorized for mobile pilot")
    if not SHA.fullmatch(evidence.candidate_sha) or evidence.release_id != "release-" + evidence.candidate_sha[:16]:
        raise PermissionError("mobile approval release identity does not match exact SHA")
    shown = ", ".join(evidence.affected_files[:7]) or "(no files)"
    if len(evidence.affected_files) > 7:
        shown += f" (+{len(evidence.affected_files) - 7} more)"
    # Each V2 card includes an unguessable, server-issued instance challenge.
    # Its exact value is carried only by that card's Action.Submit and the
    # private persisted request. Signed callback/host consumer BOTH verify it
    # before accepting owner or CCC authority. A manufactured activity.value
    # containing only approval_id and decision cannot satisfy this contract.
    if policy.schema_version == "2.0":
        challenge = card_challenge if card_challenge is not None else secrets.token_hex(24)
        if type(challenge) is not str or re.fullmatch(r"[0-9a-f]{48}", challenge) is None:
            raise PermissionError("reviewed release requires a valid card-instance challenge")
    elif card_challenge is not None:
        raise PermissionError("legacy release cannot supply a protected card challenge")
    else:
        challenge = None
    intent = {
        "release_id": evidence.release_id,
        "candidate_sha": evidence.candidate_sha,
        "rollback_sha": evidence.rollback_sha,
        "manifest_sha256": evidence.manifest_sha256,
        "purpose_sha256": digest(evidence.purpose),
        "policy_sha256": evidence.policy_sha256,
        "desired_state_policy_digest": evidence.desired_state_policy_digest,
        "owner_policy_sha256": policy.policy_sha256,
    }
    return ApprovalRequest(
        approval_id=REQUEST_PREFIX + secrets.token_hex(16),
        request_id="mobile-release:" + evidence.release_id,
        correlation_id="mobile-release:" + evidence.candidate_sha,
        organization_id=policy.organization_id,
        client_id=None,
        requested_by="svc-jason-release-manager",
        capability=CAPABILITY,
        requested_mode="release:" + evidence.candidate_sha,
        requested_at=instant,
        expires_at=instant + timedelta(seconds=policy.ttl_seconds),
        authorized_approver_ids=policy.owner_identity_ids,
        presentation=ApprovalPresentation(
            title="Production + CCC: " + evidence.purpose[:90],
            summary="Review this exact immutable release. Approve authorizes only this SHA's "
                    "release and CCC material review; independent checks, deployment and rollback remain mandatory.",
            facts=(
                ("Purpose", evidence.purpose),
                ("Release", evidence.release_id),
                ("Exact SHA", evidence.candidate_sha),
                ("Highest risk", evidence.risk_profile),
                ("Affected services", ", ".join(evidence.affected_surfaces)),
                ("Changed files", shown),
                ("Rollback", evidence.rollback_sha),
                ("Preproduction and rollback", "Passed"),
                ("Release policy", evidence.policy_sha256),
                ("Manifest fingerprint", evidence.manifest_sha256),
            ),
        ),
        metadata={
            **intent, "intent_sha256": digest(intent), "owner_policy_sha256": policy.policy_sha256,
            **({
                "card_instance_challenge": challenge,
                "card_instance_challenge_sha256": hashlib.sha256(
                    challenge.encode("ascii")
                ).hexdigest(),
            } if challenge is not None else {}),
        },
    )


class MobileReleaseSignedEvidenceStore:
    """Private immutable signed-gateway payload retained for host revalidation.

    Storing it before atomic decision consumption lets the host reject both
    forged SQLite receipts and a crashed callback without a signed payload.
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS mobile_release_signed_evidence (
              approval_id TEXT PRIMARY KEY,
              signed_envelope_json TEXT NOT NULL,
              evidence_sha256 TEXT NOT NULL
            )""")
        os.chmod(self.path, 0o600)

    def save(self, *, approval_id: str, signed_envelope: Mapping[str, Any],
             evidence_sha256: str) -> None:
        if not approval_id.startswith(REQUEST_PREFIX):
            raise ValueError("mobile signed evidence requires exact approval ID")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256):
            raise ValueError("signed Teams evidence digest invalid")
        body = canonical_bytes(dict(signed_envelope)).decode("utf-8")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT signed_envelope_json,evidence_sha256 FROM mobile_release_signed_evidence WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if existing is not None and existing != (body, evidence_sha256):
                raise PermissionError("a different Teams decision already owns this approval ID")
            if existing is None:
                self.db.execute(
                    "INSERT INTO mobile_release_signed_evidence VALUES(?,?,?)",
                    (approval_id, body, evidence_sha256),
                )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise


@dataclass
class MobileReleaseApprovalFlow:
    """A real signed Teams callback may consume one immutable request, never deploy."""
    approvals: ApprovalRequestService
    requests: Any
    policy_path: Path
    state_root: Path
    bindings: Any
    identities: Any
    signed_verifier: Any
    signed_evidence: MobileReleaseSignedEvidenceStore
    required_policy_version: str = "1.0"

    def handle(self, *, approval_id: str, decision: str, microsoft_tenant_id: str,
               microsoft_object_id: str, conversation_id: str, channel_response_id: str,
               decided_at: datetime, selections: Mapping[str, str] | None = None,
               signed_envelope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if (not approval_id.startswith(REQUEST_PREFIX) or signed_envelope is None
                or decision not in {"approve", "deny"}):
            raise PermissionError("exact signed mobile release decision required")
        # Bounded emergency hold does not affect Teams chat or other workflows.
        read_release_approval_containment(self.state_root).require_can_issue()
        token = json.dumps(dict(signed_envelope), separators=(",", ":"), ensure_ascii=False)
        machine, parsed = self.signed_verifier.parse(token)
        submit = parsed.approval_submit
        if (submit is None or submit.approval_id != approval_id or submit.decision != decision
                or parsed.microsoft_tenant_id != microsoft_tenant_id
                or parsed.microsoft_object_id != microsoft_object_id
                or parsed.conversation_id != conversation_id
                or submit.channel_response_id != channel_response_id
                or parsed.issued_at != decided_at
                or parsed.documents
                or dict(submit.selections) != dict(selections or {})):
            raise PermissionError("Teams decision does not match signed immutable approval evidence")
        principal = self.signed_verifier.verify(token)
        binding = self.bindings.find(microsoft_tenant_id=principal.tenant_id, microsoft_object_id=principal.object_id)
        if binding is None or binding.status != "active":
            raise PermissionError("mobile release approver lacks active Teams identity binding")
        identity = self.identities.get(binding.jason_identity_id)
        if identity is None or identity.status != "active" or identity.organization_id != "aot":
            raise PermissionError("mobile release approver identity not active in AOT")
        policy = read_mobile_release_policy(self.policy_path)
        if policy.schema_version != self.required_policy_version:
            raise PermissionError("Teams owner release policy changed without the reviewed runtime mode")
        if identity.identity_id not in policy.owner_identity_ids:
            raise PermissionError("mobile release actor is not the authorized owner")
        request = self.requests.get(approval_id)
        if request is None or request.status is not ApprovalRequestStatus.PENDING:
            raise PermissionError("mobile release decision is missing or already terminal")
        read_release_approval_containment(self.state_root).require_request_eligible(
            request.requested_at
        )
        if (request.organization_id != policy.organization_id or request.client_id is not None
                or request.requested_by == identity.identity_id or request.requested_by != "svc-jason-release-manager"
                or request.capability != CAPABILITY or request.authorized_approver_ids != policy.owner_identity_ids
                or request.metadata.get("owner_policy_sha256") != policy.policy_sha256):
            raise PermissionError("mobile approval requester, role or policy has changed")
        release_id = request.metadata.get("release_id", "")
        current = read_eligible_release(self.state_root, release_id, policy)
        if policy.schema_version == "2.0":
            proof = request.metadata.get("card_instance_challenge")
            if (type(proof) is not str or re.fullmatch(r"[0-9a-f]{48}", proof) is None
                    or hashlib.sha256(proof.encode("ascii")).hexdigest()
                        != request.metadata.get("card_instance_challenge_sha256")
                    or dict(submit.selections) != {"card_challenge": proof}):
                raise PermissionError("signed Teams decision is not bound to the issued card instance")
            expected = create_mobile_release_request(
                current, policy, now=request.requested_at, card_challenge=proof,
            )
        else:
            if submit.selections:
                raise PermissionError("legacy release approval cannot change immutable card material")
            expected = create_mobile_release_request(current, policy, now=request.requested_at)
        # The issuer durably records the *transport receipt* after calling
        # TeamsGatewayPlaybookApprovalSender.send(). That single field cannot
        # appear in the immutable reviewed intent reconstructed above. Do not
        # mistake its presence for a policy/manifest change and reject every
        # genuine phone click. Accept no other mutable metadata fields.
        verified_metadata = dict(request.metadata)
        delivery_receipt = verified_metadata.pop("delivery_message_ids", None)
        if delivery_receipt is not None and (
            type(delivery_receipt) is not str
            or re.fullmatch(r"[!-~]{1,512}", delivery_receipt) is None
        ):
            raise PermissionError("mobile Teams delivery receipt is invalid")
        if (expected.requested_mode != request.requested_mode
                or expected.metadata != verified_metadata
                or expected.presentation != request.presentation
                or expected.expires_at != request.expires_at):
            raise PermissionError("release contents or approval policy changed after Teams card issuance")
        # Recheck shared hold immediately before any durable signed decision
        # artifact. The independent host consumer repeats this control.
        read_release_approval_containment(self.state_root).require_request_eligible(
            request.requested_at
        )
        self.signed_evidence.save(
            approval_id=approval_id,
            signed_envelope=signed_envelope,
            evidence_sha256=principal.authentication_evidence_hash,
        )
        read_release_approval_containment(self.state_root).require_request_eligible(
            request.requested_at
        )
        accepted = self.approvals.accept_response(
            ApprovalResponse(approval_id=approval_id, organization_id=policy.organization_id,
                approver_identity_id=identity.identity_id, decision=ApprovalDecision(decision),
                decided_at=decided_at, channel="microsoft_teams",
                channel_response_id=channel_response_id,
                authentication_evidence_hash=principal.authentication_evidence_hash))
        # A durable approved receipt is NOT the release or CCC material review.
        # A distinct attestation consumer must independently revalidate and
        # materialize the exact release and CCC records. Never claim deployed.
        return {
            "status": "completed", "approval_id": approval_id,
            "approval_status": accepted.status, "executed": False,
            "reply": {"text": (
                "Approval recorded. Exact release and CCC evidence awaits independent verification; "
                "Jason has not deployed this change."
                if accepted.status == "approved"
                else "Denied. Neither production release nor CCC approval was granted."
            )},
        }


@dataclass(frozen=True, slots=True)
class MobileReleaseOwnerAuthority:
    """Policy scoped to an owner and one exact release, not shared Datto roles."""
    policy_path: Path

    def can_approve(self, *, approver_identity_id: str, organization_id: str,
                    client_id: str | None, capability: str, requested_mode: str) -> bool:
        policy = read_mobile_release_policy(self.policy_path)
        return (
            approver_identity_id in policy.owner_identity_ids
            and organization_id == policy.organization_id and client_id is None
            and capability == CAPABILITY
            and re.fullmatch(r"release:[0-9a-f]{40}", requested_mode) is not None
        )


@dataclass
class MobileReleaseApprovalMaintenance:
    """One actionable owner card per exact eligible release; no reminder spam."""
    enabled: bool
    policy_path: Path
    state_root: Path
    requests: Any
    approvals: ApprovalRequestService
    sender: TeamsGatewayPlaybookApprovalSender
    interval_seconds: int = 300
    clock: Any = lambda: datetime.now(timezone.utc)
    _next_due: datetime | None = None
    required_policy_version: str = "1.0"

    def tick(self) -> bool:
        if not self.enabled:
            return False
        containment = read_release_approval_containment(self.state_root)
        if containment.active:
            # Distinct auditable reason; never interfere with ordinary Teams,
            # site diagnostics or tickets. The shared host consumer also gates.
            _LOG.warning('OWNER_RELEASE_APPROVAL_HOLD_ACTIVE=%s', containment.hold_id)
            return False
        if self.interval_seconds < 60:
            raise ValueError("release approval scan cadence must be at least 60 seconds")
        now = self.clock()
        if self._next_due is not None and now < self._next_due:
            return False
        self._next_due = now + timedelta(seconds=self.interval_seconds)
        policy = read_mobile_release_policy(self.policy_path)
        if policy.schema_version != self.required_policy_version:
            raise PermissionError("Teams release policy changed without the reviewed runtime activation")
        paths = tuple(sorted((self.state_root / "mobile-release-offers").glob("release-*.json"),
                             key=lambda p: p.stat().st_mtime, reverse=True))[:20]
        existing_ids = {
            request.metadata.get("release_id")
            for request in self.requests.list_all()
            if request.capability == CAPABILITY
        }
        for path in paths:
            try:
                offer = json.loads(path.read_text(encoding="utf-8"))
                offered = datetime.fromisoformat(str(offer.get("published_at") or ""))
                if (offer.get("schema_version") != "1.0"
                        or offer.get("release_id") != path.stem
                        or not SHA.fullmatch(str(offer.get("candidate_sha") or ""))
                        or offer.get("release_id") != "release-" + offer["candidate_sha"][:16]
                        or offer.get("protected_main_sha") != offer["candidate_sha"]
                        or offered.tzinfo is None
                        or not 0 <= (now - offered).total_seconds() <= 900):
                    continue
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if (containment.released_at is not None
                    and offered <= containment.released_at):
                # An offer created before/during a hold may not be revived.
                continue
            if path.stem in existing_ids:
                # Terminal cards are never silently reissued. A fresh review
                # requires a separately recorded owner/release request.
                continue
            try:
                evidence = read_eligible_release(self.state_root, path.stem, policy)
            except (ValueError, PermissionError, FileNotFoundError, json.JSONDecodeError):
                continue
            if (evidence.candidate_sha != offer["candidate_sha"]
                    or evidence.rollback_sha != offer.get("live_rollback_sha")
                    or evidence.manifest_sha256 != offer.get("manifest_sha256")):
                continue
            read_release_approval_containment(self.state_root).require_request_eligible(now)
            request = create_mobile_release_request(evidence, policy, now=now)
            self.approvals.create(request, now=now)
            # A failed delivery leaves one durable pending request, not a loop
            # that spams new cards or bypasses Teams unavailable failure.
            read_release_approval_containment(self.state_root).require_request_eligible(
                request.requested_at
            )
            receipts = self.sender.send(request)
            if len(receipts) != len(policy.owner_identity_ids):
                raise RuntimeError("mobile Teams approval was not delivered to every bound owner")
            self.requests.put(replace(
                request, metadata={
                    **request.metadata,
                    "delivery_message_ids": ",".join(receipts),
                },
            ))
            return True
        return False

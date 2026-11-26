"""Verify one original Teams decision against a root-enrolled exact objective.

This adapter reuses the existing Teams signature and canonical plan format.
It does not issue an Owner credential or execute a release. Only an installed
root consumer may load enrollment, policy, revocation and prior-step facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
import json
import re
from typing import Any, Callable, Mapping

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
LICENSED_OWNER = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_CHALLENGE = re.compile(r"[0-9a-f]{48}\Z")
_APPROVAL = re.compile(r"planapproval-(?:objective-)?[0-9a-f]{32}\Z")
_REQUEST_FIELDS = frozenset({
    "schema_version", "approval_id", "plan_fingerprint", "material",
    "card_instance_challenge", "provider_message_id", "staged_at",
})
_CAPABILITIES = frozenset({
    "release.documentation.publisher.restore",
    "release.documentation.publisher.verify",
})
_ARGS = frozenset({
    "component_id", "candidate_sha", "rollback_sha", "scope_sha256",
    "manifest_sha256", "freeze_sha256", "hold_sha256",
})
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class TeamsObjectiveDenied(PermissionError):
    pass


def need(value: bool, code: str) -> None:
    if not value:
        raise TeamsObjectiveDenied("TEAMS_OBJECTIVE_" + code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def plan_digest(material: Any) -> str:
    # Match the existing PlanRequestRepository fingerprint byte for byte.
    return sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def timestamp(value: Any) -> datetime:
    try:
        at = datetime.fromisoformat(value)
        need(at.tzinfo is not None and at.utcoffset() is not None, "NAIVE_TIME")
        return at
    except (ValueError, TypeError) as exc:
        raise TeamsObjectiveDenied("TEAMS_OBJECTIVE_INVALID_TIME") from exc


@dataclass(frozen=True, slots=True)
class VerifiedTeamsObjective:
    approval_id: str
    plan_fingerprint: str
    owner_oid: str
    owner_identity_id: str
    evidence_sha256: str
    decided_at: datetime
    expires_at: datetime

    def claim_id(self, index: int, material: Mapping[str, Any]) -> str:
        return sha256(canonical({
            "approval_id": self.approval_id,
            "plan_fingerprint": self.plan_fingerprint,
            "step_index": index,
            "step_material": material,
        })).hexdigest()


def validate_enrollment(enrollment: Mapping[str, Any], *, policy_digest: str,
                        allowed_components: frozenset[str],
                        delivery_required: bool = True) -> tuple[dict, tuple[dict, ...]]:
    need(isinstance(enrollment, Mapping) and set(enrollment) == _REQUEST_FIELDS,
         "ENROLLMENT_SCHEMA")
    need(enrollment["schema_version"] == "1.0"
         and isinstance(enrollment["approval_id"], str)
         and _APPROVAL.fullmatch(enrollment["approval_id"]) is not None,
         "ENROLLMENT_ID")
    need(isinstance(enrollment["card_instance_challenge"], str)
         and _CHALLENGE.fullmatch(enrollment["card_instance_challenge"]) is not None,
         "ENROLLMENT_CHALLENGE")
    message = enrollment["provider_message_id"]
    if delivery_required:
        need(type(message) is str and 1 <= len(message) <= 256
             and not message.startswith("accepted:") and not any(c.isspace() for c in message),
             "UNVERIFIED_PROVIDER_MESSAGE")
    else:
        need(message is None, "UNDELIVERED_ENROLLMENT_HAS_MESSAGE")
    material = enrollment["material"]
    need(isinstance(material, dict) and set(material) == {"requests", "scope"}
         and len(canonical(material)) <= 65536, "MATERIAL_SCHEMA")
    need(plan_digest(material) == enrollment["plan_fingerprint"],
         "MATERIAL_FINGERPRINT")
    scope = material["scope"]
    need(isinstance(scope, dict)
         and set(scope) == {"plan_id", "organization_id", "policy_digest",
                            "allowed_capabilities", "allowed_clients", "max_risk",
                            "production_allowed", "expires_at"}
         and scope["organization_id"] == "aot"
         and scope["plan_id"] == "plan-" + enrollment["approval_id"]
         and scope["policy_digest"] == policy_digest
         and scope["production_allowed"] is True
         and scope["allowed_clients"] == []
         and type(scope["max_risk"]) is int and scope["max_risk"] == 3,
         "ROOT_POLICY_OR_SCOPE")
    steps = material["requests"]
    need(isinstance(steps, list) and 1 <= len(steps) <= 12
         and all(isinstance(s, dict) for s in steps), "STEP_COUNT")
    need(all(type(s.get("capability_name")) is str
             and type(s.get("execution_id")) is str and s["execution_id"]
             and type(s.get("principal_id")) is str and s["principal_id"] for s in steps),
         "STEP_IDENTIFIERS")
    need(scope["allowed_capabilities"] == sorted({s["capability_name"] for s in steps}),
         "CAPABILITY_SCOPE")
    need(len({s.get("execution_id") for s in steps}) == len(steps),
         "DUPLICATE_EXECUTION_ID")
    requesters = {s.get("principal_id") for s in steps}
    need(len(requesters) == 1 and all(type(s) is str and s for s in requesters),
         "REQUESTER_SCOPE")
    for step in steps:
        need(step.get("organization_id") == "aot" and step.get("client_id") is None
             and step.get("requester_kind") == "service"
             and step.get("permission_mode") == "execute"
             and step.get("requested_mode") == "deterministic"
             and step.get("orchestration_mode") == "execute"
             and step.get("risk") == "critical"
             and step.get("authority_allowed") is False
             and step.get("approval_present") is False
             and step.get("authority_context_id") is None
             and step.get("approval_id") is None
             and step.get("capability_name") in _CAPABILITIES
             and step.get("capability_version") == "1.0.0",
             "UNREVIEWED_STEP")
        args = step.get("arguments")
        need(isinstance(args, dict) and set(args) == _ARGS
             and args["component_id"] in allowed_components
             and all(type(args[k]) is str and _SHA.fullmatch(args[k]) is not None
                     for k in ("candidate_sha", "rollback_sha"))
             and args["candidate_sha"] != args["rollback_sha"]
             and all(type(args[k]) is str and _HEX.fullmatch(args[k]) is not None
                     for k in ("scope_sha256", "manifest_sha256", "freeze_sha256", "hold_sha256")),
             "EXACT_ARTIFACT_SCOPE")
    staged, expires = timestamp(enrollment["staged_at"]), timestamp(scope["expires_at"])
    need(timedelta(0) < expires - staged <= timedelta(hours=24), "PLAN_LIFETIME")
    return scope, tuple(steps)


def verify_original_teams_decision(
    *, enrollment: Mapping[str, Any], signed_envelope: Mapping[str, Any],
    authenticator: Any, allowed_machine_identities: frozenset[str],
    policy_digest: str, allowed_components: frozenset[str],
    current_owner_identity: Callable[[str, str], str | None],
    at: datetime, previously_verified_at: datetime | None = None,
) -> VerifiedTeamsObjective:
    """Root must supply its immutable enrollment and prior verification time.

    A signature is checked against the original decision time after enrollment;
    the root-owned record, current identity, policy and plan expiry remain live.
    No unsigned ledger row or caller-supplied prior-step list is authority.
    """
    need(isinstance(at, datetime) and at.tzinfo is not None, "CURRENT_TIME")
    scope, _ = validate_enrollment(enrollment, policy_digest=policy_digest,
                                   allowed_components=allowed_components)
    need(timestamp(enrollment["staged_at"]) <= at < timestamp(scope["expires_at"]),
         "PLAN_EXPIRED_OR_FUTURE")
    need(isinstance(signed_envelope, Mapping)
         and len(canonical(signed_envelope)) <= 65536, "SIGNED_RESPONSE_BOUND")
    try:
        machine = authenticator.authenticate(signed_envelope)
    except Exception as exc:
        raise TeamsObjectiveDenied("TEAMS_OBJECTIVE_GATEWAY_SIGNATURE") from exc
    need(machine in allowed_machine_identities, "GATEWAY_NOT_REGISTERED")
    envelope = signed_envelope
    identity = envelope.get("transport_identity")
    interaction = envelope.get("interaction")
    need(envelope.get("kind") == "conversation.turn"
         and envelope.get("channel") == "msteams"
         and isinstance(identity, dict) and isinstance(interaction, dict),
         "SIGNED_RESPONSE_SCHEMA")
    need(identity.get("microsoft_tenant_id") == TENANT
         and identity.get("microsoft_object_id") == LICENSED_OWNER
         and identity.get("authentication_assurance") == "botframework-authenticated",
         "OWNER_IDENTITY")
    owner = current_owner_identity(TENANT, LICENSED_OWNER)
    need(type(owner) is str and bool(owner), "CURRENT_OWNER_INACTIVE")
    need(interaction.get("kind") == "approval.submit"
         and interaction.get("approval_id") == enrollment["approval_id"]
         and interaction.get("decision") == "approve"
         and interaction.get("channel_response_id") == envelope.get("message_id")
         and type(envelope.get("message_id")) is str and bool(envelope["message_id"])
         and type(envelope.get("conversation_id")) is str and bool(envelope["conversation_id"]),
         "EXACT_APPROVAL_RESPONSE")
    selections = interaction.get("selections")
    need(isinstance(selections, dict) and set(selections) == {"card_challenge"}
         and type(selections["card_challenge"]) is str
         and hmac.compare_digest(selections["card_challenge"],
                                 enrollment["card_instance_challenge"]),
         "ORIGINAL_CARD_CHALLENGE")
    # This SDK-authenticated field must be outside editable card selections.
    need(interaction.get("callback_reply_to_id") == enrollment["provider_message_id"],
         "ORIGINAL_PROVIDER_MESSAGE_LINK")
    issued, expires = timestamp(envelope.get("issued_at")), timestamp(envelope.get("expires_at"))
    verified_at = at if previously_verified_at is None else previously_verified_at
    need(isinstance(verified_at, datetime) and verified_at.tzinfo is not None
         and timestamp(enrollment["staged_at"]) <= issued <= verified_at
         and issued <= verified_at < expires
         and timedelta(0) < expires - issued <= timedelta(seconds=180)
         and timedelta(0) <= verified_at - issued <= timedelta(seconds=120)
         and verified_at <= at,
         "DECISION_FRESHNESS")
    return VerifiedTeamsObjective(
        enrollment["approval_id"], enrollment["plan_fingerprint"], LICENSED_OWNER,
        owner, sha256(canonical({k: v for k, v in envelope.items() if k != "signature"})).hexdigest(),
        verified_at, timestamp(scope["expires_at"]),
    )

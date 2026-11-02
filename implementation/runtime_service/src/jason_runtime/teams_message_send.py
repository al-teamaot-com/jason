from __future__ import annotations
import json, os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from kernel.capabilities import CapabilityApproval, CapabilityDefinition, CapabilityEvidence, CapabilityLifecycle, CapabilityRisk, CapabilityStewardship, IdempotencyBehavior
from kernel.execution_deadline import bounded_execution_timeout
from kernel.execution_providers import ExecutionProvider, ProviderApproval, ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits, ProviderStewardship, ProviderType
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan, normalize_provider_relative_path
from orchestrator.service import InvocationResult

CAPABILITY="communication.teams.message.send"
PROVIDER="microsoft_teams_gateway"
PROFILE="owner-proactive-v1"

@dataclass(frozen=True, slots=True)
class _PreparedTeamsMessageSend:
    gateway_url: str
    token: str
    payload: dict


def post_existing_teams_gateway(
    *, gateway_url: str, token: str, payload: dict,
    timeout_seconds: float = 20,
) -> dict:
    """One production transport for every approved Teams sender.

    This is the existing managed Teams provider POST, NOT a policy/authority
    check. All callers must establish their governance before invocation.
    Never retry an ambiguous Teams POST or claim a human approved on send.
    """
    if (not isinstance(gateway_url, str) or not gateway_url.strip()
            or not isinstance(token, str) or not token.strip()
            or not isinstance(payload, dict)):
        raise PermissionError("configured Teams transport unavailable")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    if len(body) > 65536:
        raise ValueError("Teams gateway payload exceeds bound")
    req = Request(
        gateway_url.rstrip("/") + "/internal/proactive/send",
        data=body, method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"},
    )
    with urlopen(req, timeout=bounded_execution_timeout(timeout_seconds)) as response:
        result = json.loads(response.read().decode("utf-8"))
    if (not isinstance(result, dict) or result.get("status") != "succeeded"
            or not isinstance(result.get("message_id"), str)
            or not result["message_id"].strip()):
        raise RuntimeError("Teams proactive send failed")

    # The SDK sometimes returns no provider message ID for Adaptive Cards.
    # The gateway then returns accepted:<UUID>, which is only an acceptance
    # reference, not a Teams message ID or evidence the person was notified.
    message_id = result["message_id"].strip()
    synthetic = result.get("message_id_synthetic", message_id.startswith("accepted:"))
    if type(synthetic) is not bool or synthetic != message_id.startswith("accepted:"):
        raise RuntimeError("Teams gateway supplied inconsistent send evidence")
    evidence_type = result.get(
        "delivery_evidence_type",
        "provider_call_completed_without_message_id" if synthetic else "provider_message_id",
    )
    expected_type = (
        "provider_call_completed_without_message_id" if synthetic else "provider_message_id"
    )
    if evidence_type != expected_type:
        raise RuntimeError("Teams gateway supplied inconsistent receipt type")
    return {
        **result,
        "message_id": message_id,
        "message_id_synthetic": synthetic,
        "delivery_evidence_type": evidence_type,
    }


@dataclass
class TeamsMessageSendInvoker:
    gateway_url: str
    token_file: str
    def _validated_payload(self, *, request, resolution):
        if request.capability_name != CAPABILITY or resolution.selected_provider_id != PROVIDER:
            raise PermissionError("Teams send provider/capability mismatch")
        args = dict(request.arguments or {})
        allowed = {"aad_object_id", "tenant_id", "text", "card"}
        if set(args) - allowed:
            raise ValueError("unsupported Teams message arguments")
        aad = str(args.get("aad_object_id", "")).strip()
        tenant = str(args.get("tenant_id", "")).strip()
        text = str(args.get("text", "")).strip()
        if not aad or not tenant or not text or len(text) > 12000:
            raise ValueError("invalid Teams message request")
        payload = {"aadObjectId": aad, "tenantId": tenant, "text": text}
        card = args.get("card")
        if card is not None:
            if not isinstance(card, dict) or card.get("type") != "AdaptiveCard":
                raise ValueError("invalid Teams adaptive card")
            payload["card"] = card
        return aad, tenant, payload

    def prepare_execution_plan(self, *, request, resolution):
        aad, tenant, payload = self._validated_payload(request=request, resolution=resolution)
        token = Path(self.token_file).read_text().strip()
        if not token:
            raise PermissionError("Teams proactive token unavailable")
        path = "/internal/proactive/send"
        plan = ExecutionPlan(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            canonical_capability=request.capability_name,
            selected_provider_id=PROVIDER,
            provider_capability=CAPABILITY,
            action_method="POST",
            resource_type="microsoft_teams_conversation",
            resource_identifier=f"{tenant}:{aad}",
            normalized_path=path,
            normalized_payload=payload,
            material_parameters={},
            symbolic_resolutions={},
        )
        return PreparedExecutionPlan(
            plan=plan,
            opaque=_PreparedTeamsMessageSend(
                gateway_url=self.gateway_url.rstrip("/"),
                token=token,
                payload=payload,
            ),
        )

    def invoke_execution_plan(self, *, request, resolution, prepared):
        aad, tenant, payload = self._validated_payload(request=request, resolution=resolution)
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedTeamsMessageSend):
            raise PermissionError("invalid Teams prepared execution")
        plan = prepared.plan
        if plan.selected_provider_id != PROVIDER or plan.provider_capability != CAPABILITY:
            raise PermissionError("prepared Teams provider binding changed")
        if plan.action_method != "POST":
            raise PermissionError("prepared Teams method changed")
        if normalize_provider_relative_path(plan.normalized_path) != "/internal/proactive/send":
            raise PermissionError("prepared Teams path changed")
        if plan.resource_identifier != f"{tenant}:{aad}":
            raise PermissionError("prepared Teams target changed")
        if dict(plan.normalized_payload) != payload or opaque.payload != payload:
            raise PermissionError("prepared Teams payload changed")
        result = post_existing_teams_gateway(
            gateway_url=opaque.gateway_url,
            token=opaque.token,
            payload=payload,
        )
        return InvocationResult(
            output={
                "provider": PROVIDER,
                "channel": "microsoft_teams",
                "message_id": result["message_id"],
                "conversation_id": result.get("conversation_id"),
                "bootstrap_created": bool(result.get("bootstrap_created", False)),
                "message_id_synthetic": result["message_id_synthetic"],
                "delivery_evidence_type": result["delivery_evidence_type"],
                "delivery_state": (
                    "provider_accepted_delivery_unverified"
                    if result["message_id_synthetic"] else "provider_accepted"
                ),
            },
            attempts=1,
        )

    def invoke(self, *, request, resolution):
        return self.invoke_execution_plan(
            request=request,
            resolution=resolution,
            prepared=self.prepare_execution_plan(request=request, resolution=resolution),
        )


def register_foundation(*,capabilities,providers,now:datetime):
    cap=CapabilityDefinition(capability_name=CAPABILITY,version="1.0",display_name="Send Governed Microsoft Teams Message",lifecycle_status=CapabilityLifecycle.BUILDING,business_purpose="Send one governed proactive Microsoft Teams message to an enabled AOT Entra member, automatically bootstrapping the Jason Teams app/conversation when required.",owner_service="Jason Governed Actions",architectural_capability_ids=frozenset({"JAC-005","JAC-006"}),risk_level=CapabilityRisk.HIGH,data_classifications=frozenset({"internal"}),permitted_execution_modes=frozenset({"deterministic"}),input_schema_reference="schema://jason/communication-teams-message-send/1.0",output_schema_reference="schema://jason/communication-teams-message-send-result/1.0",invoking_roles=frozenset({"orchestrator"}),approval=CapabilityApproval(required=True,approver_classes=("owner",)),evidence=CapabilityEvidence(required=True,requirements=("authenticated requester identity","validated Microsoft tenant identity","enabled AOT member target identity","Jason Teams app installation state","stored or newly created authenticated Teams conversation reference","provider message id"),verification_requirements=("target tenant matches AOT tenant","target is an enabled member before bootstrap side effects","exactly one provider message send attempt")),dependencies=frozenset({"identity.authorization.resolve","governance.action.evaluate"}),idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,idempotency_key_required=True,timeout_seconds=30,maximum_attempts=1,failure_behavior="Fail closed without recipient substitution or retry.",tenant_isolation_required=True,client_isolation_required=False,stewardship=CapabilityStewardship(steward="technology-steward",business_justification="Permit governed proactive Teams communication through the existing Jason Teams gateway.",review_interval_days=30,retirement_criteria=("Tenant isolation cannot be proven.",),authoritative_change_sources=("Microsoft Agents SDK",),last_reviewed_at=now,operational_owner="AOT IT Operations",approval_owner="AOT Owner"),created_at=now,metadata={"provider_neutral":"true","read_only":"false","write_capability":"true","resource_types":"communication_message,microsoft_teams","operation":"send","mcp_action_enabled":"true","mcp_tool_name":"execute_governed_capability","conversation_authenticated_imperative_is_approval":"true"})
    capabilities.register(cap)
    provider=ExecutionProvider(provider_id=PROVIDER,display_name="Jason Microsoft Teams Gateway",provider_type=ProviderType.EXTERNAL_CONNECTOR,lifecycle_status=ProviderLifecycle.PLANNED,health_status=ProviderHealth.UNKNOWN,approval_status=ProviderApproval.PILOT,execution_modes=frozenset({"deterministic"}),capabilities=frozenset({CAPABILITY}),supported_classifications=frozenset({"internal"}),regions=frozenset(),limits=ProviderLimits(maximum_concurrent_executions=1,maximum_requests_per_minute=30,maximum_execution_seconds=30),features=ProviderFeatures(structured_output=True),pricing_profile_id="zero-cost-foundation",stewardship=ProviderStewardship(technology_steward="technology-steward",business_justification="Use the existing direct Teams gateway for outbound Jason messages.",review_interval_days=30,last_reviewed_at=now,retirement_criteria=("Gateway tenant containment fails.",),vendor_change_sources=("Microsoft Agents SDK",),operational_owner="AOT IT Operations",approval_owner="AOT Owner"),created_at=now,metadata={"write_capability":"true"})
    providers.register(provider)
    if os.getenv("JASON_TEAMS_MESSAGE_SEND_MCP_PROFILE","").strip().casefold()==PROFILE:
        capabilities.set_lifecycle(capability_name=CAPABILITY,version="1.0",lifecycle_status=CapabilityLifecycle.ACTIVE)
        providers.set_approval(provider_id=PROVIDER,approval_status=ProviderApproval.APPROVED); providers.set_health(provider_id=PROVIDER,health_status=ProviderHealth.HEALTHY); providers.set_lifecycle(provider_id=PROVIDER,lifecycle_status=ProviderLifecycle.AVAILABLE)

def build_invoker():
    return TeamsMessageSendInvoker(gateway_url=os.getenv("JASON_TEAMS_GATEWAY_INTERNAL_URL","http://jason-teams-gateway:3979"),token_file=os.getenv("JASON_TEAMS_PROACTIVE_TOKEN_FILE","/run/jason-secrets/teams-proactive-gateway/token"))

from __future__ import annotations
import json, os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from kernel.capabilities import CapabilityApproval, CapabilityDefinition, CapabilityEvidence, CapabilityLifecycle, CapabilityRisk, CapabilityStewardship, IdempotencyBehavior
from kernel.execution_providers import ExecutionProvider, ProviderApproval, ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits, ProviderStewardship, ProviderType
from orchestrator.service import InvocationResult

CAPABILITY="communication.teams.message.send"
PROVIDER="microsoft_teams_gateway"
PROFILE="owner-proactive-v1"

@dataclass
class TeamsMessageSendInvoker:
    gateway_url: str
    token_file: str
    def invoke(self, *, request, resolution):
        if request.capability_name != CAPABILITY or resolution.selected_provider_id != PROVIDER:
            raise PermissionError("Teams send provider/capability mismatch")
        args=dict(request.arguments or {})
        allowed={"aad_object_id","tenant_id","text"}
        if set(args)-allowed: raise ValueError("unsupported Teams message arguments")
        aad=str(args.get("aad_object_id","")).strip(); tenant=str(args.get("tenant_id","")).strip(); text=str(args.get("text","")).strip()
        if not aad or not tenant or not text or len(text)>12000: raise ValueError("invalid Teams message request")
        token=Path(self.token_file).read_text().strip()
        if not token: raise PermissionError("Teams proactive token unavailable")
        body=json.dumps({"aadObjectId":aad,"tenantId":tenant,"text":text}).encode()
        req=Request(self.gateway_url.rstrip("/")+"/internal/proactive/send",data=body,method="POST",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        with urlopen(req,timeout=20) as response: result=json.loads(response.read().decode())
        if result.get("status")!="succeeded" or not result.get("message_id"): raise RuntimeError("Teams proactive send failed")
        return InvocationResult(output={"provider":PROVIDER,"channel":"microsoft_teams","message_id":result["message_id"]},attempts=1)

def register_foundation(*,capabilities,providers,now:datetime):
    cap=CapabilityDefinition(capability_name=CAPABILITY,version="1.0",display_name="Send Governed Microsoft Teams Message",lifecycle_status=CapabilityLifecycle.BUILDING,business_purpose="Send one governed proactive Microsoft Teams message to a previously authenticated Teams conversation.",owner_service="Jason Governed Actions",architectural_capability_ids=frozenset({"JAC-005","JAC-006"}),risk_level=CapabilityRisk.HIGH,data_classifications=frozenset({"internal"}),permitted_execution_modes=frozenset({"deterministic"}),input_schema_reference="schema://jason/communication-teams-message-send/1.0",output_schema_reference="schema://jason/communication-teams-message-send-result/1.0",invoking_roles=frozenset({"orchestrator"}),approval=CapabilityApproval(required=True,approver_classes=("owner",)),evidence=CapabilityEvidence(required=True,requirements=("authenticated requester identity","validated Microsoft tenant identity","stored authenticated Teams conversation reference","provider message id"),verification_requirements=("target tenant matches stored conversation tenant","exactly one provider send attempt")),dependencies=frozenset({"identity.authorization.resolve","governance.action.evaluate"}),idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,idempotency_key_required=True,timeout_seconds=30,maximum_attempts=1,failure_behavior="Fail closed without recipient substitution or retry.",tenant_isolation_required=True,client_isolation_required=False,stewardship=CapabilityStewardship(steward="technology-steward",business_justification="Permit governed proactive Teams communication through the existing Jason Teams gateway.",review_interval_days=30,retirement_criteria=("Tenant isolation cannot be proven.",),authoritative_change_sources=("Microsoft Agents SDK",),last_reviewed_at=now,operational_owner="AOT IT Operations",approval_owner="AOT Owner"),created_at=now,metadata={"provider_neutral":"true","read_only":"false","write_capability":"true","resource_types":"communication_message,microsoft_teams","operation":"send","mcp_action_enabled":"true","mcp_tool_name":"execute_governed_capability","conversation_authenticated_imperative_is_approval":"true"})
    capabilities.register(cap)
    provider=ExecutionProvider(provider_id=PROVIDER,display_name="Jason Microsoft Teams Gateway",provider_type=ProviderType.EXTERNAL_CONNECTOR,lifecycle_status=ProviderLifecycle.PLANNED,health_status=ProviderHealth.UNKNOWN,approval_status=ProviderApproval.PILOT,execution_modes=frozenset({"deterministic"}),capabilities=frozenset({CAPABILITY}),supported_classifications=frozenset({"internal"}),regions=frozenset(),limits=ProviderLimits(maximum_concurrent_executions=1,maximum_requests_per_minute=30,maximum_execution_seconds=30),features=ProviderFeatures(structured_output=True),pricing_profile_id="zero-cost-foundation",stewardship=ProviderStewardship(technology_steward="technology-steward",business_justification="Use the existing direct Teams gateway for outbound Jason messages.",review_interval_days=30,last_reviewed_at=now,retirement_criteria=("Gateway tenant containment fails.",),vendor_change_sources=("Microsoft Agents SDK",),operational_owner="AOT IT Operations",approval_owner="AOT Owner"),created_at=now,metadata={"write_capability":"true"})
    providers.register(provider)
    if os.getenv("JASON_TEAMS_MESSAGE_SEND_MCP_PROFILE","").strip().casefold()==PROFILE:
        capabilities.set_lifecycle(capability_name=CAPABILITY,version="1.0",lifecycle_status=CapabilityLifecycle.ACTIVE)
        providers.set_approval(provider_id=PROVIDER,approval_status=ProviderApproval.APPROVED); providers.set_health(provider_id=PROVIDER,health_status=ProviderHealth.HEALTHY); providers.set_lifecycle(provider_id=PROVIDER,lifecycle_status=ProviderLifecycle.AVAILABLE)

def build_invoker():
    return TeamsMessageSendInvoker(gateway_url=os.getenv("JASON_TEAMS_GATEWAY_INTERNAL_URL","http://jason-teams-gateway:3979"),token_file=os.getenv("JASON_TEAMS_PROACTIVE_TOKEN_FILE","/run/jason-secrets/teams-proactive/token"))

"""Real issuer -> authenticated callback -> persisted worker; no live provider writes."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import json

import pytest

from kernel.capabilities import CapabilityLifecycle,CapabilityRisk
from orchestrator.teams_conversation_flow import BoundConversationPrincipal, ConversationIntent, TeamsConversationPrincipalEvidence, ConversationGuidanceRequiredError
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory, ConversationAuthorityError
from jason_runtime.universal_teams_approval import UniversalApprovalPolicyFile
from jason_runtime.universal_plan_issuance import UniversalPlanIssuer,ExistingTeamsApprovalDelivery
from test_universal_teams_approval_runtime import setup,NOW,click,signed,seed,grant_verification_step


class RegisteredCapabilities:
    def get_current(self,*,capability_name,allow_pilot):
        return SimpleNamespace(capability_name=capability_name,version='1.0',
            lifecycle_status=CapabilityLifecycle.ACTIVE,risk_level=CapabilityRisk.LOW,
            permitted_execution_modes=frozenset({'deterministic'}),idempotency_key_required=True,metadata={})


class Delivery:
    def __init__(self): self.requests=[]
    def deliver(self,request):
        from orchestrator.approval_delivery import ApprovalDeliveryReceipt
        self.requests.append(request)
        return ApprovalDeliveryReceipt('microsoft_teams','message-1,message-2',NOW)


def identity():
    return TeamsConversationPrincipalEvidence('tenant','object-requester-a','botframework-authenticated',
                                              'requester-conversation','requester-message')


def with_issuer(env):
    delivery=Delivery()
    issuer=UniversalPlanIssuer(env.handler,UniversalApprovalPolicyFile(env.policy),
        env.handler.service.teams_flow.resume_bridge.authority,RegisteredCapabilities(),env.bindings,delivery,
        clock=lambda:NOW,approval_id_factory=lambda:'planapproval-issued')
    env.handler=replace(env.handler,issuer=issuer)
    return delivery,issuer


def test_normal_factory_sends_real_approval_and_never_executes_before_click(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler,
        execution_id_factory=lambda:'normal-execution',clock=lambda:NOW)
    intent=ConversationIntent('synthetic.resource.read',{'resource_id':'controlled-test'})
    with pytest.raises(ConversationGuidanceRequiredError,match='universal_approval_requested') as caught:
        factory.build(principal=BoundConversationPrincipal('requester-a','org','client'),
            intent=intent,identity=identity(),correlation_id='normal-correlation')
    assert 'Approval sent' in caught.value.guidance_text
    assert len(delivery.requests)==1 and not env.provider.calls
    pending=delivery.requests[0]
    assert pending.authorized_approver_ids==('approver-a','approver-b')
    assert pending.expires_at==NOW+timedelta(minutes=30)
    plan=env.handler.proposals.require(pending.approval_id)
    assert plan.scope.expires_at==pending.expires_at
    assert env.handler.requests.require(pending.approval_id).capability_version=='1.0'
    assert env.handler.requests.require(pending.approval_id).data_handling.retention_allowed
    assert click(env,signed(env,plan))['status']=='approved'
    assert env.handler.plan_runner.tick()
    assert len(env.provider.calls)==1
    assert env.handler.requests.progress(pending.approval_id)['state']=='completed'


def test_requester_without_jkd_grant_cannot_trigger_delivery(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    with pytest.raises(ConversationAuthorityError):
        factory.build(principal=BoundConversationPrincipal('outsider','wrong-org','client'),
            intent=ConversationIntent('synthetic.resource.read'),identity=identity(),correlation_id='corr')
    assert not delivery.requests


def test_standing_authority_read_does_not_get_unnecessary_approval(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    evidence=replace(identity(),microsoft_object_id='object-approver-a')
    result=factory.build(principal=BoundConversationPrincipal('approver-a','org','client'),
        intent=ConversationIntent('synthetic.resource.read'),identity=evidence,correlation_id='corr')
    assert result.authority_allowed
    assert not delivery.requests and not env.provider.calls


def test_explicit_retention_policy_required_before_card_delivery(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    policy=json.loads(env.policy.read_text());policy['organizations']['org']['request_retention_allowed']=False
    env.policy.write_text(json.dumps(policy))
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    with pytest.raises(PermissionError,match='retention'):
        factory.build(principal=BoundConversationPrincipal('requester-a','org','client'),
            intent=ConversationIntent('synthetic.resource.read'),identity=identity(),correlation_id='corr')
    assert not delivery.requests


def test_embedded_secret_cannot_be_retained_or_sent_to_approver(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    with pytest.raises(ValueError,match='credential'):
        factory.build(principal=BoundConversationPrincipal('requester-a','org','client'),
            intent=ConversationIntent('synthetic.resource.read',{'password':'synthetic'}),identity=identity(),correlation_id='corr')
    assert not delivery.requests


def test_partial_delivery_is_not_reported_as_success(tmp_path):
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    class Sender:
        def __init__(self,**kwargs): pass
        def send(self,request):return ('only-one-message',)
    channel=ExistingTeamsApprovalDelivery('http://synthetic-gateway',tmp_path/'no-token-needed',env.bindings,Sender,lambda:NOW)
    issuer=replace(issuer,delivery=channel)
    env.handler=replace(env.handler,issuer=issuer)
    factory=GovernedTeamsOrchestrationRequestFactory(
        authority=issuer.authority,capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    with pytest.raises(RuntimeError,match='every selected recipient'):
        factory.build(principal=BoundConversationPrincipal('requester-a','org','client'),
            intent=ConversationIntent('synthetic.resource.read'),identity=identity(),correlation_id='corr')
    assert env.handler.requests.progress('planapproval-issued')['reason_code']=='approval_delivery_RuntimeError'
    assert not env.provider.calls


def test_actual_adaptive_card_actions_are_accepted_by_actual_gateway_parser(tmp_path):
    from pathlib import Path
    import subprocess
    from connectors.microsoft_graph.teams_approval_channel import render_approval_card
    from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
    env=setup(tmp_path);delivery,issuer=with_issuer(env)
    factory=GovernedTeamsOrchestrationRequestFactory(authority=issuer.authority,
        capabilities=RegisteredCapabilities(),approval_requester=env.handler)
    with pytest.raises(ConversationGuidanceRequiredError):
        factory.build(principal=BoundConversationPrincipal('requester-a','org','client'),
            intent=ConversationIntent('synthetic.resource.read'),identity=identity(),correlation_id='corr')
    card=TeamsGatewayPlaybookApprovalSender._adaptive_card(render_approval_card(delivery.requests[0]))
    values=[a['data'] for a in card['actions']]
    assert all(set(v)=={'approval_id','decision'} for v in values)
    root=Path(__file__).resolve().parents[3]
    module=(root/'infrastructure/jason-teams-gateway/approval-submit.mjs')
    # Python is installed under implementation/runtime_service/tests; resolve repository root.
    if not module.exists():
        root=root.parent;module=root/'infrastructure/jason-teams-gateway/approval-submit.mjs'
    script='import { parseApprovalSubmit } from '+json.dumps(module.as_uri())+'; let s=""; for await (const c of process.stdin) s+=c; const a=JSON.parse(s).map(parseApprovalSubmit); if(a.some(x=>x===null)) process.exit(7); console.log(JSON.stringify(a));'
    result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(values),
        capture_output=True,text=True,timeout=10,check=True)
    parsed=json.loads(result.stdout)
    assert [v['decision'] for v in parsed]==['approve','deny','request_changes']
    assert all(not v['selections'] for v in parsed)

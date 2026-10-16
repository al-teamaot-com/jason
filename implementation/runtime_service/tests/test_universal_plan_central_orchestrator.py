"""Universal approval through actual JKD, resolution and Central Orchestrator.

The only substituted execution component is the external provider transport. No
customer system is called and this is not live Teams/Microsoft acceptance.
"""
from dataclasses import replace

import pytest

from kernel.capabilities import CapabilityRegistryService,InMemoryCapabilityRegistry,CapabilityLifecycle
from kernel.execution_policy import ExecutionPolicyEngine,CostEstimator,InMemoryPricingRegistry
from kernel.execution_providers import (ExecutionProviderRegistryService,InMemoryExecutionProviderRegistry,
    ProviderHealth,ProviderLifecycle,ProviderApproval)
from kernel.identity_authority import ExecutionContextValidator,SQLiteIdentityAuthorityStore
from kernel.resolution import GovernedCapabilityResolutionEngine
from orchestrator.authority import JKD001OrchestrationContextEnforcer
from orchestrator.execution_plan import ExecutionPlan,PreparedExecutionPlan
from orchestrator.provider_read_capability_catalog import register_provider_read_foundation,SERVICE_TICKET_SEARCH,AUTOTASK_PROVIDER
from orchestrator.service import CentralOrchestrator,InvocationResult
from test_universal_teams_approval_runtime import setup,seed,signed,click,rebuild,NOW,grant_verification_step


class SyntheticProvider:
    def __init__(self, *, wrong_provider=False):
        self.calls=[]
        self.wrong_provider=wrong_provider
    def prepare_execution_plan(self, *, request,resolution):
        return PreparedExecutionPlan(ExecutionPlan(
            principal_id=request.principal_id,organization_id=request.organization_id,
            client_id=request.client_id,canonical_capability=request.capability_name,
            selected_provider_id='wrong-provider' if self.wrong_provider else resolution.selected_provider_id,
            provider_capability='synthetic.resource.read',action_method='GET',
            resource_type='synthetic_resource',resource_identifier=request.arguments['resource_id'],
            normalized_path='/synthetic/read',normalized_payload=dict(request.arguments)))
    def invoke_execution_plan(self, *, request,resolution,prepared):
        assert request.authority_context_id and request.approval_id
        self.calls.append((request,prepared.plan))
        return InvocationResult(output={'verified':True,'resource_id':request.arguments['resource_id']},attempts=1)
    def invoke(self, **kwargs):
        raise AssertionError('approval execution must use the concrete prepared plan')


class Audit:
    def __init__(self): self.events=[]
    def append(self,event_type,payload): self.events.append((event_type,dict(payload)))


def real_central(env,tmp_path,*,wrong_provider=False):
    capabilities=CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers=ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(capabilities=capabilities,providers=providers,now=NOW)
    prototype=capabilities.get_current(capability_name=SERVICE_TICKET_SEARCH,allow_pilot=True)
    for name in ('synthetic.resource.read','synthetic.resource.verify'):
        capabilities.register(replace(prototype,capability_name=name,
            lifecycle_status=CapabilityLifecycle.ACTIVE))
    provider=providers.get(AUTOTASK_PROVIDER)
    providers.register(replace(provider,provider_id='synthetic-provider',display_name='Synthetic integration provider',
        capabilities=frozenset({'synthetic.resource.read','synthetic.resource.verify'}),health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,lifecycle_status=ProviderLifecycle.AVAILABLE))
    resolution=GovernedCapabilityResolutionEngine(capabilities=capabilities,providers=providers,
        policy=ExecutionPolicyEngine(cost_estimator=CostEstimator(InMemoryPricingRegistry())))
    invoker=SyntheticProvider(wrong_provider=wrong_provider)
    audit=Audit()
    central=CentralOrchestrator(resolution=resolution,invoker=invoker,audit=audit,
        authority_context=JKD001OrchestrationContextEnforcer(ExecutionContextValidator(
            SQLiteIdentityAuthorityStore(tmp_path/'authority.db'),clock=lambda:NOW)),
        require_authority_context=True,governed_execution_ledger=env.execution_ledger)
    env.provider=central
    env.handler=rebuild(env,tmp_path)
    return invoker,audit


def test_one_signed_approval_executes_through_actual_central_gates(tmp_path):
    env=setup(tmp_path);grant_verification_step(env)
    provider,audit=real_central(env,tmp_path)
    plan=seed(env,extra_step=True)
    assert click(env,signed(env,plan))['status']=='completed'
    assert env.handler.plan_runner.tick()
    progress=env.handler.requests.progress(plan.approval_id)
    assert progress['state']=='completed',progress
    assert [r.capability_name for r,_ in provider.calls]==['synthetic.resource.read','synthetic.resource.verify']
    assert len({r.authority_context_id for r,_ in provider.calls})==2
    for request,_ in provider.calls:
        evidence=env.execution_ledger.evidence(request.approval_id)
        assert evidence['state']=='succeeded'
        assert evidence['parent_approval_id']==plan.approval_id
        assert evidence['approved_plan_fingerprint']==plan.plan_fingerprint
        assert evidence['execution_plan_fingerprint']
    assert len([e for e in audit.events if e[0]=='orchestration.capability.completed'])==2
    assert rebuild(env,tmp_path).plan_runner.tick() is False
    assert len(provider.calls)==2


def test_changed_provider_plan_rejected_before_any_provider_invocation(tmp_path):
    env=setup(tmp_path)
    provider,audit=real_central(env,tmp_path,wrong_provider=True)
    plan=seed(env)
    click(env,signed(env,plan))
    assert env.handler.plan_runner.tick()
    assert not provider.calls
    progress=env.handler.requests.progress(plan.approval_id)
    assert progress['state']=='blocked',progress
    assert any('denied' in name or 'invalid' in name for name,_ in audit.events)


def test_completed_provider_result_recovers_without_second_invocation(tmp_path,monkeypatch):
    env=setup(tmp_path)
    provider,audit=real_central(env,tmp_path)
    plan=seed(env)
    click(env,signed(env,plan))
    def crash_before_small_receipt(*args,**kwargs):
        raise SystemExit('synthetic stop after canonical provider completion')
    monkeypatch.setattr(env.handler.requests,'record_step_result',crash_before_small_receipt)
    with pytest.raises(SystemExit):
        env.handler.plan_runner.tick()
    assert len(provider.calls)==1
    resumed=rebuild(env,tmp_path)
    assert resumed.plan_runner.tick()
    assert resumed.requests.progress(plan.approval_id)['state']=='completed'
    assert len(provider.calls)==1

import sqlite3
from dataclasses import replace
from test_universal_teams_approval_runtime import setup,seed,signed,click,NOW
from jason_runtime.universal_plan_status import UniversalPlanStatusMaintenance


class Sender:
    calls=[]
    fail=False
    def __init__(self,**kwargs):self.targets=kwargs['owner_identity_ids']
    def send_status(self,*,text):
        self.calls.append((self.targets,text))
        if self.fail:raise TimeoutError('synthetic uncertain delivery')
        return ('message-confirmation',)


def maintenance(env):
    return UniversalPlanStatusMaintenance(env.handler,env.bindings,env.identities,Sender,
        'http://synthetic','not-used',clock=lambda:NOW)


def completed(env):
    plan=seed(env);click(env,signed(env,plan));env.handler.plan_runner.tick();return plan


def test_success_report_reaches_only_original_participants_once(tmp_path):
    Sender.calls=[];Sender.fail=False
    env=setup(tmp_path);plan=completed(env)
    assert maintenance(env).tick()
    assert {targets[0] for targets,_ in Sender.calls}=={'requester-a','approver-a'}
    assert all('finished successfully' in text and 'controlled-test' not in text for _,text in Sender.calls)
    assert maintenance(env).tick() is False
    assert len(Sender.calls)==2


def test_notification_timeout_preserves_completion_and_is_not_replayed(tmp_path):
    Sender.calls=[];Sender.fail=True
    env=setup(tmp_path);plan=completed(env)
    assert maintenance(env).tick()
    assert env.handler.requests.progress(plan.approval_id)['state']=='completed'
    assert maintenance(env).tick() is False
    with sqlite3.connect(env.handler.requests.path) as db:
        assert db.execute('SELECT DISTINCT delivery_status FROM universal_plan_status_deliveries').fetchall()==[('indeterminate',)]
    Sender.fail=False


def test_revoked_participant_does_not_get_status(tmp_path):
    Sender.calls=[];Sender.fail=False
    env=setup(tmp_path);completed(env)
    actor=env.identities.get('approver-a')
    env.identities.put(replace(actor,status='disabled'))
    assert maintenance(env).tick()
    assert [r for r,_ in Sender.calls]==[('requester-a',)]


def _service_result(tmp_path, *, decision='approve'):
    from test_universal_service_plan_issuance import service_env, issue
    env, _, issuer, request = service_env(tmp_path)
    issued = issue(issuer, request)
    plan = env.handler.proposals.require(issued['approval_id'])
    click(env, signed(env, plan, decision=decision))
    # The normal continuation worker records the terminal state after the
    # signed callback. It runs for Deny as well as Approve.
    assert env.handler.plan_runner.tick()
    assert env.handler.requests.progress(plan.approval_id)['state'] == (
        'completed' if decision == 'approve' else 'denied'
    )
    return env, plan


def test_service_plan_completion_notifies_only_its_authenticated_decider(tmp_path):
    Sender.calls=[]; Sender.fail=False
    env, plan = _service_result(tmp_path)
    # A service principal has no human Microsoft Teams binding to notify.
    assert env.bindings.find_active_by_jason_identity(jason_identity_id='worker') is None
    assert maintenance(env).tick()
    assert [targets for targets, _ in Sender.calls] == [('approver-a',)]
    assert 'finished successfully' in Sender.calls[0][1]
    assert plan.approval_id in Sender.calls[0][1]
    assert maintenance(env).tick() is False
    assert len(Sender.calls) == 1
    assert len(env.provider.calls) == 1


def test_service_plan_denial_notifies_only_decider_and_never_executes(tmp_path):
    Sender.calls=[]; Sender.fail=False
    env, plan = _service_result(tmp_path, decision='deny')
    assert env.handler.requests.progress(plan.approval_id)['state'] == 'denied'
    assert maintenance(env).tick()
    assert [targets for targets, _ in Sender.calls] == [('approver-a',)]
    assert 'not executed' in Sender.calls[0][1]
    assert maintenance(env).tick() is False
    assert env.provider.calls == []


def test_service_plan_status_fails_closed_if_workload_tenant_changes(tmp_path):
    import json
    Sender.calls=[]; Sender.fail=False
    env, _ = _service_result(tmp_path)
    policy=json.loads(env.policy.read_text())
    policy['organizations']['org']['service_requesters']['worker']['microsoft_tenant_id']='different-tenant'
    env.policy.write_text(json.dumps(policy))
    assert maintenance(env).tick() is False
    assert Sender.calls == []


def test_service_plan_status_never_infers_a_tenant_without_current_policy(tmp_path):
    import json
    Sender.calls=[]; Sender.fail=False
    env, _ = _service_result(tmp_path)
    policy=json.loads(env.policy.read_text())
    del policy['organizations']['org']['service_requesters']
    env.policy.write_text(json.dumps(policy))
    assert maintenance(env).tick() is False
    assert Sender.calls == []

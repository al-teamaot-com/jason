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

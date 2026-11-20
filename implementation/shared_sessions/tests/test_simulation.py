import json
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from implementation.shared_sessions.events import SessionEventLedger
from implementation.shared_sessions.grants import SingleUseGrantPrototype, GrantScope
from implementation.shared_sessions.lifecycle import SessionLifecycle
from implementation.shared_sessions.policy import SessionPolicy, SessionRequest
from implementation.shared_sessions.simulation import OfflineSessionSimulator

class OfflineSimulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'policy.json'
        self.conf={'schema_version':1,'enabled':True,'configuration_version':'test',
                   'transports':{'ssh':True},'modes':{'guided':True}}
        path.write_text(json.dumps(self.conf))
        self.path=path
        self.req=SessionRequest('tenant','client','device','tech','ticket','ssh','guided','read_only',
            governed_grant_valid=True,identity_verified=True,target_binding_verified=True,
            execution_transport_approved=True)
        self.grants=SingleUseGrantPrototype(b'only-an-isolated-test-secret-123456')
        self.ledger=SessionEventLedger()
        self.life=SessionLifecycle(self.ledger)
        self.life.open(tenant_id='tenant',session_id='s',technician_id='tech',target_id='device',ticket_id='ticket')
        self.sim=OfflineSessionSimulator(policy=SessionPolicy(path),grants=self.grants,
                                          ledger=self.ledger,lifecycle=self.life)
        self.command='Get-Service'
        self.scope=GrantScope('tenant','client','device','tech','ticket','ssh',sha256(self.command.encode()).hexdigest())

    def test_matching_grant_never_executes(self):
        token=self.grants.issue_for_test(self.scope)
        result=self.sim.propose(session_id='s',request=self.req,command_text=self.command,token=token)
        self.assertTrue(result.authorized_for_simulation)
        self.assertFalse(result.executed)
        self.assertFalse(self.sim.propose(session_id='s',request=self.req,command_text=self.command,token=token).authorized_for_simulation)
        self.assertNotIn(self.command,str(self.ledger.history(tenant_id='tenant',session_id='s')))

    def test_denied_even_with_valid_grant_when_policy_disabled(self):
        self.path.write_text(json.dumps(self.conf|{'enabled':False}))
        token=self.grants.issue_for_test(self.scope)
        self.assertFalse(self.sim.propose(session_id='s',request=self.req,command_text=self.command,token=token).authorized_for_simulation)

    def test_paused_or_wrong_technician_cannot_propose(self):
        token=self.grants.issue_for_test(self.scope)
        self.assertFalse(self.sim.propose(session_id='s',request=replace(self.req,technician_id='another'),command_text=self.command,token=token).authorized_for_simulation)
        self.life.transition(tenant_id='tenant',session_id='s',technician_id='tech',action='pause')
        self.assertFalse(self.sim.propose(session_id='s',request=self.req,command_text=self.command,token=token).authorized_for_simulation)

    def test_digest_binds_exact_command(self):
        token=self.grants.issue_for_test(self.scope)
        self.assertFalse(self.sim.propose(session_id='s',request=self.req,command_text='Get-Process',token=token).authorized_for_simulation)

import unittest
from implementation.shared_sessions.events import SessionEventLedger
from implementation.shared_sessions.lifecycle import SessionLifecycle

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ledger = SessionEventLedger()
        self.manager = SessionLifecycle(self.ledger)
        self.params = dict(tenant_id='a', session_id='s', technician_id='tech', target_id='device', ticket_id='ticket')

    def test_lifecycle_open_pause_revoke_and_no_reopen(self):
        self.assertEqual(self.manager.open(**self.params).state, 'active')
        self.assertEqual(self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='pause').state, 'paused')
        self.assertEqual(self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='revoke').state, 'revoked')
        with self.assertRaises(ValueError):
            self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='close')
        with self.assertRaises(ValueError):
            self.manager.open(**self.params)
        self.assertEqual([e.kind for e in self.ledger.history(tenant_id='a',session_id='s')],
                         ['session_opened','session_paused','session_revoked'])

    def test_identity_and_tenant_separation(self):
        self.manager.open(**self.params)
        for tenant,tech in [('b','tech'),('a','other')]:
            with self.subTest(tenant=tenant,tech=tech),self.assertRaises(PermissionError):
                self.manager.inspect(tenant_id=tenant,session_id='s',technician_id=tech)
            with self.subTest(tenant=tenant,tech=tech),self.assertRaises(PermissionError):
                self.manager.transition(tenant_id=tenant,session_id='s',technician_id=tech,action='revoke')
        self.assertEqual(self.manager.inspect(tenant_id='a',session_id='s',technician_id='tech').state,'active')

    def test_no_missing_context_or_invalid_transition(self):
        with self.assertRaises(ValueError):
            self.manager.open(**(self.params | {'target_id':''}))
        self.manager.open(**self.params)
        with self.assertRaises(ValueError):
            self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='resume')
        self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='close')
        with self.assertRaises(ValueError):
            self.manager.transition(tenant_id='a',session_id='s',technician_id='tech',action='pause')

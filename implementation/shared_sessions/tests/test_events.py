import unittest
from implementation.shared_sessions.events import SessionEventLedger

class LedgerTests(unittest.TestCase):
    def test_open_then_ordered_evidence(self):
        ledger = SessionEventLedger()
        original = {'safe': ['one']}
        opening = ledger.append(tenant_id='tenant-a', session_id='s1', kind='session_opened', evidence=original)
        original['safe'].append('two')
        event = ledger.append(tenant_id='tenant-a', session_id='s1', kind='decision_recorded', evidence={'decision':'deny'})
        self.assertEqual(opening.evidence, {'safe':['one']})
        self.assertEqual(event.sequence, 2)
        self.assertEqual(event.previous_digest, opening.digest)
        self.assertEqual(len(ledger.history(tenant_id='tenant-a', session_id='s1')), 2)
        self.assertEqual(ledger.history(tenant_id='tenant-b', session_id='s1'), ())

    def test_no_unopened_or_reopened_session(self):
        ledger = SessionEventLedger()
        with self.assertRaises(ValueError):
            ledger.append(tenant_id='a', session_id='s', kind='command_started', evidence={})
        ledger.append(tenant_id='a', session_id='s', kind='session_opened', evidence={})
        with self.assertRaises(ValueError):
            ledger.append(tenant_id='a', session_id='s', kind='session_opened', evidence={})

    def test_revocation_and_close_terminal(self):
        for terminal in ('session_revoked', 'session_closed'):
            with self.subTest(terminal=terminal):
                ledger = SessionEventLedger()
                ledger.append(tenant_id='a', session_id='s', kind='session_opened', evidence={})
                ledger.append(tenant_id='a', session_id='s', kind=terminal, evidence={})
                with self.assertRaises(ValueError):
                    ledger.append(tenant_id='a', session_id='s', kind='command_proposed', evidence={})

    def test_unknown_event_or_invalid_payload_fails_closed(self):
        ledger = SessionEventLedger()
        for kwargs in ({'kind':'unknown','evidence':{}}, {'kind':'session_opened','evidence':object()}):
            with self.assertRaises(ValueError):
                ledger.append(tenant_id='a', session_id='s', **kwargs)

    def test_returned_events_cannot_modify_internal_evidence(self):
        ledger = SessionEventLedger()
        returned = ledger.append(tenant_id='a', session_id='s', kind='session_opened', evidence={'items':['original']})
        returned.evidence['items'].append('tampered')
        history = ledger.history(tenant_id='a',session_id='s')
        history[0].evidence['items'].append('tampered again')
        self.assertEqual(ledger.history(tenant_id='a',session_id='s')[0].evidence, {'items':['original']})
        self.assertTrue(ledger.verify(tenant_id='a',session_id='s'))

    def test_chain_verification_detects_internal_corruption(self):
        ledger = SessionEventLedger()
        ledger.append(tenant_id='a',session_id='s',kind='session_opened',evidence={})
        ledger.append(tenant_id='a',session_id='s',kind='session_paused',evidence={'reason':'test'})
        self.assertTrue(ledger.verify(tenant_id='a',session_id='s'))
        ledger._events[('a','s')][1].evidence['reason'] = 'changed'
        self.assertFalse(ledger.verify(tenant_id='a',session_id='s'))

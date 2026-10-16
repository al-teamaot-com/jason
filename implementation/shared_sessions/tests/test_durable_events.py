import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from implementation.shared_sessions.durable_events import SqliteSessionEventLedger

class DurableEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'session.db'
        self.ledger=SqliteSessionEventLedger(self.path)

    def test_survives_reopen_and_separates_tenants(self):
        first=self.ledger.append(tenant_id='a',session_id='s',kind='session_opened',evidence={'id':'t'})
        reopened=SqliteSessionEventLedger(self.path)
        second=reopened.append(tenant_id='a',session_id='s',kind='session_paused',evidence={'reason':'test'})
        self.assertEqual(second.sequence,2)
        self.assertEqual(second.previous_digest,first.digest)
        self.assertEqual(len(reopened.history(tenant_id='a',session_id='s')),2)
        self.assertEqual(reopened.history(tenant_id='b',session_id='s'),())
        self.assertTrue(reopened.verify(tenant_id='a',session_id='s'))

    def test_terminal_and_duplicate_are_rejected_after_restart(self):
        self.ledger.append(tenant_id='a',session_id='s',kind='session_opened',evidence={})
        with self.assertRaises(ValueError):
            self.ledger.append(tenant_id='a',session_id='s',kind='session_opened',evidence={})
        self.ledger.append(tenant_id='a',session_id='s',kind='session_revoked',evidence={})
        with self.assertRaises(ValueError):
            SqliteSessionEventLedger(self.path).append(tenant_id='a',session_id='s',kind='command_proposed',evidence={})

    def test_tamper_detection_and_no_unopened_event(self):
        with self.assertRaises(ValueError):
            self.ledger.append(tenant_id='a',session_id='s',kind='command_started',evidence={})
        self.ledger.append(tenant_id='a',session_id='s',kind='session_opened',evidence={'id':'t'})
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE session_events SET evidence_json='{}' WHERE tenant_id='a'")
        self.assertFalse(self.ledger.verify(tenant_id='a',session_id='s'))

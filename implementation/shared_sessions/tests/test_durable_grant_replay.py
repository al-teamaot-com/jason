import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from implementation.shared_sessions.durable_grant_replay import SqliteGrantReplayStore

class DurableGrantReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'grants.db'
        self.ledger=SqliteGrantReplayStore(self.path)
        self.digest='a'*64

    def test_persisted_one_time_use(self):
        self.assertTrue(self.ledger.consume(token_digest=self.digest,exp=110,now=100))
        restarted=SqliteGrantReplayStore(self.path)
        self.assertFalse(restarted.consume(token_digest=self.digest,exp=110,now=101))
        self.assertEqual(restarted.status(self.digest),'used')

    def test_revocation_cannot_be_consumed(self):
        self.assertTrue(self.ledger.revoke(token_digest=self.digest,exp=110,now=100))
        self.assertFalse(SqliteGrantReplayStore(self.path).consume(token_digest=self.digest,exp=110,now=100))
        self.assertEqual(self.ledger.status(self.digest),'revoked')

    def test_expiry_and_malformed_denied(self):
        self.assertFalse(self.ledger.consume(token_digest=self.digest,exp=100,now=100))
        for invalid in (None,'x',123):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.ledger.consume(token_digest=invalid,exp=110,now=100)

    def test_atomic_same_token_concurrent_consumption(self):
        def claim(_):
            return SqliteGrantReplayStore(self.path).consume(token_digest=self.digest,exp=110,now=100)
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(claim,range(12)))
        self.assertEqual(sum(results),1)

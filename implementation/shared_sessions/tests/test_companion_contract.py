import unittest
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from implementation.shared_sessions.companion_contract import CompanionIdentity,CompanionHandshake

class CompanionContractTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,16,tzinfo=timezone.utc)
        self.identity=CompanionIdentity('aot-internal','aot','claw2-datto-uid','claw2-pc','install-1','fingerprint-1','windows')
        self.handshake=CompanionHandshake(self.identity,self.now,self.now+timedelta(minutes=2),
                                         'test-nonce-at-least-16',True,True,True,True)

    def test_matching_identity_and_proofs(self):
        self.assertTrue(self.handshake.check(expected=self.identity,now=self.now))
        self.assertFalse(self.handshake.check(expected=replace(self.identity,hostname='other'),now=self.now))

    def test_fail_closed_without_each_proof(self):
        for name in ('authenticated','tenant_binding_verified','device_binding_verified','key_proof_verified','engineering_only'):
            with self.subTest(name=name):
                self.assertFalse(replace(self.handshake,**{name:False}).check(expected=self.identity,now=self.now))

    def test_expiration_window_and_malformed_proofs(self):
        self.assertFalse(self.handshake.check(expected=self.identity,now=self.now+timedelta(minutes=2)))
        self.assertFalse(replace(self.handshake,expires_at=self.now+timedelta(minutes=10)).check(expected=self.identity,now=self.now))
        self.assertFalse(replace(self.handshake,authenticated='yes').check(expected=self.identity,now=self.now))
        self.assertFalse(replace(self.handshake,nonce='short').check(expected=self.identity,now=self.now))

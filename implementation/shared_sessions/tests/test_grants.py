import unittest
from datetime import datetime, timezone, timedelta
from dataclasses import replace
from implementation.shared_sessions.grants import GrantScope, SingleUseGrantPrototype

class GrantsTests(unittest.TestCase):
    def setUp(self):
        self.time = datetime(2026,10,16,tzinfo=timezone.utc)
        self.manager = SingleUseGrantPrototype(b'only-an-isolated-test-secret-123456',now=lambda:self.time)
        self.scope = GrantScope('tenant','client','device','tech','ticket','ssh','a'*64)

    def test_matching_token_once_only(self):
        token = self.manager.issue_for_test(self.scope)
        self.assertTrue(self.manager.consume(token,self.scope))
        self.assertFalse(self.manager.consume(token,self.scope))

    def test_scope_binding_all_fields(self):
        token = self.manager.issue_for_test(self.scope)
        for name in vars(self.scope):
            with self.subTest(field=name):
                self.assertFalse(self.manager.consume(token,replace(self.scope,**{name:'other'})))
        self.assertTrue(self.manager.consume(token,self.scope))

    def test_signature_and_revocation(self):
        token = self.manager.issue_for_test(self.scope)
        self.assertFalse(self.manager.consume(token[:-3]+'XYZ',self.scope))
        self.assertTrue(self.manager.revoke(token))
        self.assertFalse(self.manager.consume(token,self.scope))

    def test_expired_and_forged_grants(self):
        token = self.manager.issue_for_test(self.scope, lifetime_seconds=1)
        self.time += timedelta(seconds=1)
        self.assertFalse(self.manager.consume(token,self.scope))
        self.assertFalse(self.manager.consume('not-a-token',self.scope))
        other = SingleUseGrantPrototype(b'another-test-signing-secret-123456',now=lambda:self.time)
        self.assertFalse(other.consume(token,self.scope))

    def test_invalid_expiry_and_scope(self):
        with self.assertRaises(ValueError):
            self.manager.issue_for_test(self.scope,lifetime_seconds=301)
        with self.assertRaises(ValueError):
            self.manager.issue_for_test(replace(self.scope,tenant_id=''))

    def test_malformed_base64_is_denied_without_exceptions(self):
        self.assertFalse(self.manager.consume('@@@.###',self.scope))
        self.assertFalse(self.manager.revoke('@@@.###'))

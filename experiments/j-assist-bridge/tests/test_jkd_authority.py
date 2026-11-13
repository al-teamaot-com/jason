from __future__ import annotations

import sys
import unittest
from pathlib import Path

root=Path(__file__).resolve().parents[1]
repo=root.parents[1]
sys.path.insert(0,str(root))
sys.path.insert(0,str(repo/"implementation"))
from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, IdentityRecord,
    InMemoryApprovalRepository, InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository, PermissionMode,
)
from jkd_authority import J_ASSIST_OBSERVE_CAPABILITY, make_jkd_datto_authorizer
from session_gate import Denied, SessionGate, VerifiedTechnician


class JkdIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.identities=InMemoryIdentityRepository()
        self.grants=InMemoryAuthorityGrantRepository()
        self.identities.put(IdentityRecord("tech-a","human","aot"))
        self.identities.put(IdentityRecord("tech-b","human","aot"))
        self.authority=IdentityAuthorityService(
            identities=self.identities,grants=self.grants,
            approvals=InMemoryApprovalRepository(),
        )
        self.native_ok=True
        self.check=make_jkd_datto_authorizer(
            identity_authority=self.authority,
            native_datto_device_access=lambda principal, uid: self.native_ok and uid=="1717088",
        )
        self.gate=SessionGate(
            identity=lambda ctx: VerifiedTechnician(ctx[0],ctx[1]),
            can_read_datto_device=self.check,
        )

    def allow(self):
        self.grants.put(AuthorityGrant(
            grant_id="test-jassist-aot",subject_id="organization:aot",
            capability=J_ASSIST_OBSERVE_CAPABILITY,organization_id="aot",
            client_id=None,permission=PermissionMode.OBSERVE,
        ))

    def start(self,person=("tech-a","aot")):
        return self.gate.start(
            trusted_context=person,device_uid="1717088",consent=True,
        )

    def test_no_implicit_grant(self):
        with self.assertRaises(Denied):
            self.start()

    def test_jkd_grant_and_native_datto_both_required(self):
        self.allow()
        receipt,token=self.start()
        self.assertEqual(self.gate.acknowledge_metadata(
            trusted_context=("tech-a","aot"),session_id=receipt.session_id,
            token=token,device_uid="1717088",event="heartbeat",
        ),1)
        self.native_ok=False
        with self.assertRaises(Denied):
            self.gate.acknowledge_metadata(
                trusted_context=("tech-a","aot"),session_id=receipt.session_id,
                token=token,device_uid="1717088",event="heartbeat",
            )

    def test_jkd_revocation_ends_live_session(self):
        self.allow()
        receipt,token=self.start()
        self.grants.revoke("test-jassist-aot")
        with self.assertRaises(Denied):
            self.gate.acknowledge_metadata(
                trusted_context=("tech-a","aot"),session_id=receipt.session_id,
                token=token,device_uid="1717088",event="heartbeat",
            )

    def test_unknown_identity_denied_even_with_org_grant(self):
        self.allow()
        with self.assertRaises(Denied):
            self.start(("unregistered","aot"))

    def test_native_denial_even_with_jkd_grant(self):
        self.allow()
        self.native_ok=False
        with self.assertRaises(Denied):
            self.start()


if __name__=="__main__":
    unittest.main()

from __future__ import annotations
from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_group_screen_authority import (EntraGroupEvidence, EntraGroupScreenAuthorizer, AOT_JASSIST_PILOT_GROUP_ID)
from entra_send_authority import AOT_ENTRA_TENANT_ID
from session_gate import VerifiedTechnician

GROUP=AOT_JASSIST_PILOT_GROUP_ID # exact owner-approved pilot group
AL="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"

class GroupScreenTests(unittest.TestCase):
    def setUp(self):
        self.principal=VerifiedTechnician("canonical-al","aot")
        self.oid=AL
        self.proof=EntraGroupEvidence(AL,AOT_ENTRA_TENANT_ID,GROUP,True,True,True)
        self.calls=[]
        self.auth=EntraGroupScreenAuthorizer(
            group_id=GROUP,
            resolve_entr_user_oid=lambda p:self.oid,
            read_live_membership=lambda tenant,oid,group:self.calls.append((tenant,oid,group)) or self.proof,
            device_in_aot_account=lambda uid:uid=="1717088",
        )

    def test_membership_requires_active_account_and_device(self):
        self.assertTrue(self.auth(self.principal,"1717088"))
        self.assertEqual(self.calls,[(AOT_ENTRA_TENANT_ID,AL,GROUP)])
        self.assertFalse(self.auth(self.principal,"9999"))

    def test_deny_wrong_group_nonmember_disabled_or_unverified(self):
        for changes in (
            {"group_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
            {"user_oid":"ffffffff-ffff-4fff-8fff-ffffffffffff"},
            {"tenant_id":"foreign"},
            {"is_member":False},{"account_enabled":False},
            {"verified_by_graph":False},
        ):
            with self.subTest(changes=changes):
                self.proof=replace(EntraGroupEvidence(AL,AOT_ENTRA_TENANT_ID,GROUP,True,True,True),**changes)
                self.assertFalse(self.auth(self.principal,"1717088"))

    def test_untrusted_user_or_tenant_and_native_actions_denied(self):
        self.assertFalse(self.auth(VerifiedTechnician("other","foreign"),"1717088"))
        self.assertFalse(self.auth(("canonical-al","aot"),"1717088"))
        for surface in ("powershell","webremote","reboot","ticket_update","send","quickbooks"):
            self.assertFalse(self.auth.can_access(self.principal,"1717088",surface=surface))

    def test_stale_or_missing_identity_mapping_denies(self):
        self.oid=None
        self.assertFalse(self.auth(self.principal,"1717088"))
        self.oid="Al Davis"
        self.assertFalse(self.auth(self.principal,"1717088"))

    def test_unknown_device_and_provider_outages_fail_closed(self):
        self.assertFalse(self.auth(self.principal,"1717088/"))
        self.assertFalse(self.auth(self.principal,"invalid"))
        self.proof=None
        self.assertFalse(self.auth(self.principal,"1717088"))
        outage=EntraGroupScreenAuthorizer(
            group_id=GROUP,
            resolve_entr_user_oid=lambda p:AL,
            read_live_membership=lambda t,u,g:(_ for _ in ()).throw(RuntimeError("Graph outage")),
            device_in_aot_account=lambda d:True,
        )
        self.assertFalse(outage(self.principal,"1717088"))

    def test_dependencies_or_group_missing_denies_init(self):
        cases=(
            ("bad",lambda p:AL,lambda t,u,g:self.proof,lambda d:True),
            (GROUP,None,lambda t,u,g:self.proof,lambda d:True),
            (GROUP,lambda p:AL,None,lambda d:True),
            (GROUP,lambda p:AL,lambda t,u,g:self.proof,None),
        )
        for gid,oid,membership,device in cases:
            with self.subTest(gid=gid),self.assertRaises(ValueError):
                EntraGroupScreenAuthorizer(
                    group_id=gid,resolve_entr_user_oid=oid,
                    read_live_membership=membership,device_in_aot_account=device,
                )

if __name__=="__main__":
    unittest.main()

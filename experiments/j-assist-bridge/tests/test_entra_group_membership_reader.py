from __future__ import annotations

from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_group_membership_reader import GraphMembershipReader, GRAPH_ROOT
from entra_group_screen_authority import (
    EntraGroupScreenAuthorizer, AOT_JASSIST_PILOT_GROUP_ID as GROUP,
)
from entra_send_authority import AOT_ENTRA_TENANT_ID as TENANT
from session_gate import VerifiedTechnician

AL="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
LINDSEY="9f590a57-a07e-434b-84e9-5b698161b86a"
ADAM="d6ec61e1-7408-408c-8904-a33e82a8baa0"
OTHER="00000000-0000-4000-8000-000000000000"

class GraphGroupAdapterTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.enabled=True
        self.members={AL,LINDSEY,ADAM}
        self.uid=AL

        def get(url):
            self.calls.append(("GET",url))
            assert url == GRAPH_ROOT+"/users/"+self.uid+"?$select=id,accountEnabled"
            return {"id":self.uid,"accountEnabled":self.enabled}

        def post(url,body):
            self.calls.append(("POST",url,body))
            assert url == GRAPH_ROOT+"/users/"+self.uid+"/checkMemberGroups"
            assert body == {"groupIds":[GROUP]}
            return {"value":[GROUP] if self.uid in self.members else []}

        self.get=get
        self.post=post
        self.reader=GraphMembershipReader(get_json=self.get,post_json=self.post)

    def read(self, oid=AL):
        self.uid=oid
        return self.reader(TENANT,oid,GROUP)

    def test_all_three_real_oid_shapes_have_exact_graph_member_proof(self):
        for oid in (AL,LINDSEY,ADAM):
            with self.subTest(oid=oid):
                evidence=self.read(oid)
                self.assertTrue(evidence.is_member)
                self.assertTrue(evidence.account_enabled)
                self.assertTrue(evidence.verified_by_graph)
                self.assertEqual(evidence.user_oid,oid)

    def test_nonmember_is_denied_and_no_names_are_inferred(self):
        self.assertFalse(self.read(OTHER).is_member)
        before=len(self.calls)
        for invalid in ("al@teamaot.com","Al Davis","../users/x","", "0"*35):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.reader(TENANT,invalid,GROUP)
        self.assertEqual(len(self.calls),before)

    def test_disabled_user_skips_membership_lookup(self):
        self.enabled=False
        e=self.read(AL)
        self.assertFalse(e.is_member)
        self.assertFalse(e.account_enabled)
        self.assertEqual([row[0] for row in self.calls],["GET"])

    def test_wrong_tenant_or_group_blocks_before_graph_io(self):
        for tenant,group in ((TENANT,"bad"),("other",GROUP), (TENANT,"00000000-0000-0000-0000-000000000000")):
            with self.assertRaises(ValueError):
                self.reader(tenant,AL,group)
        self.assertEqual(self.calls,[])

    def test_server_configured_alternate_group_is_not_hard_coded(self):
        alternate="11111111-1111-4111-8111-111111111111"
        reader=GraphMembershipReader(
            get_json=lambda url:{"id":AL,"accountEnabled":True},
            post_json=lambda url,body:{"value":[alternate]} if body=={"groupIds":[alternate]}
                else (_ for _ in ()).throw(AssertionError("wrong group")))
        e=reader(TENANT,AL,alternate)
        self.assertEqual(e.group_id,alternate)
        self.assertTrue(e.is_member)

    def test_strict_profile_type_and_oid_match(self):
        profiles=(
            None,
            {"id":OTHER,"accountEnabled":True},
            {"id":AL,"accountEnabled":"true"},
            {"id":AL,"accountEnabled":1},
            {"id":AL,"accountEnabled":None},
            {"accountEnabled":True},
        )
        for response in profiles:
            with self.subTest(response=response):
                reader=GraphMembershipReader(get_json=lambda u:response,
                    post_json=lambda u,b:{"value":[GROUP]})
                with self.assertRaises(ValueError):
                    reader(TENANT,AL,GROUP)

    def test_strict_member_response_and_duplicates(self):
        for response in (None, {}, {"value":None},{"value":GROUP},
                         {"value":[GROUP,GROUP]}, {"value":[OTHER]},
                         {"value":[1]}, {"value":[None]}):
            with self.subTest(response=response):
                reader=GraphMembershipReader(
                    get_json=lambda u:{"id":AL,"accountEnabled":True},
                    post_json=lambda u,b:response)
                with self.assertRaises(ValueError):
                    reader(TENANT,AL,GROUP)

    def test_live_membership_change_is_reflected_on_next_read(self):
        self.assertTrue(self.read(AL).is_member)
        self.members.remove(AL)
        self.assertFalse(self.read(AL).is_member)
        self.assertEqual(len([x for x in self.calls if x[0]=="POST"]),2)

    def test_transport_failure_never_becomes_positive_evidence(self):
        reader=GraphMembershipReader(
            get_json=lambda u:(_ for _ in ()).throw(OSError("Graph offline")),
            post_json=lambda u,b:{"value":[GROUP]},
        )
        authorizer=EntraGroupScreenAuthorizer(
            group_id=GROUP,
            resolve_entr_user_oid=lambda person:AL,
            read_live_membership=reader,
            device_in_aot_account=lambda uid:True,
        )
        self.assertFalse(authorizer(VerifiedTechnician("al-canonical","aot"),"1717088"))

    def test_end_to_end_adapter_and_screen_only_gate(self):
        reader=self.reader
        principal=VerifiedTechnician("some-canonical-aot-technician","aot")
        auth=EntraGroupScreenAuthorizer(
            group_id=GROUP,
            resolve_entr_user_oid=lambda person:AL if person==principal else None,
            read_live_membership=reader,
            device_in_aot_account=lambda uid:uid=="1717088",
        )
        self.assertTrue(auth(principal,"1717088"))
        self.assertFalse(auth.can_access(principal,"1717088",surface="powershell"))
        self.members.clear()
        self.assertFalse(auth(principal,"1717088"))
        self.assertFalse(auth(principal,"9999999"))
        self.assertFalse(auth(VerifiedTechnician("unauthorized","aot"),"1717088"))


if __name__=="__main__":
    unittest.main()

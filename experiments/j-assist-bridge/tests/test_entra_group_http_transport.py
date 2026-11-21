from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_group_http_transport import AotGraphMembershipHttpTransport
from entra_group_membership_reader import GraphMembershipReader, GRAPH_ROOT
from entra_group_screen_authority import AOT_JASSIST_PILOT_GROUP_ID as GROUP
from entra_send_authority import AOT_ENTRA_TENANT_ID as TENANT

OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"

class Tokens:
    def __init__(self):
        self.tenants=[]
    def access_token_for_tenant(self,*,microsoft_tenant_id):
        self.tenants.append(microsoft_tenant_id)
        return "synthetic-server-only-token"

class Transport:
    def __init__(self):
        self.calls=[]
        self.member=True
        self.enabled=True
    def request(self,**kwargs):
        self.calls.append(kwargs)
        if kwargs["method"]=="GET":
            return {"id":OID,"accountEnabled":self.enabled}
        if kwargs["method"]=="POST":
            return {"value":[GROUP] if self.member else []}
        raise AssertionError("unexpected method")

class HttpAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tokens=Tokens()
        self.transport=Transport()
        self.http=AotGraphMembershipHttpTransport(tokens=self.tokens,transport=self.transport)

    def test_existing_tenant_provider_is_used_for_both_calls(self):
        reader=GraphMembershipReader(get_json=self.http.get_json,post_json=self.http.post_json)
        proof=reader(TENANT,OID,GROUP)
        self.assertTrue(proof.is_member)
        self.assertEqual(self.tokens.tenants,[TENANT,TENANT])
        self.assertEqual([x["method"] for x in self.transport.calls],["GET","POST"])
        self.assertEqual(self.transport.calls[0]["url"], GRAPH_ROOT+"/users/"+OID)
        self.assertEqual(self.transport.calls[0]["params"],{"$select":"id,accountEnabled"})
        self.assertEqual(self.transport.calls[1]["json"],{"groupIds":[GROUP]})
        self.assertTrue(all(
            x["headers"]=={"Authorization":"Bearer synthetic-server-only-token"}
            for x in self.transport.calls
        ))
        self.assertFalse(any("token" in repr(proof).lower() for _ in (1,)))
        self.transport.member=False
        self.assertFalse(reader(TENANT,OID,GROUP).is_member)

    def test_disabled_user_does_not_hit_group_check(self):
        self.transport.enabled=False
        reader=GraphMembershipReader(get_json=self.http.get_json,post_json=self.http.post_json)
        proof=reader(TENANT,OID,GROUP)
        self.assertFalse(proof.account_enabled)
        self.assertEqual([x["method"] for x in self.transport.calls],["GET"])

    def test_only_approved_graph_paths(self):
        invalid=(
            "https://example.com/v1.0/users/"+OID+"?$select=id,accountEnabled",
            "http://graph.microsoft.com/v1.0/users/"+OID+"?$select=id,accountEnabled",
            "https://graph.microsoft.com.evil/v1.0/users/"+OID+"?$select=id,accountEnabled",
            "https://graph.microsoft.com:444/v1.0/users/"+OID+"?$select=id,accountEnabled",
            "https://graph.microsoft.com/v1.0/users/"+OID+"?$select=mail",
            "https://graph.microsoft.com/v1.0/groups/"+GROUP,
            "https://graph.microsoft.com/v1.0/users/"+OID+"/manager",
            "https://graph.microsoft.com/v1.0/users/"+OID+"?$select=id,accountEnabled#fragment",
        )
        for url in invalid:
            with self.subTest(url=url),self.assertRaises(ValueError):
                self.http.get_json(url)
        self.assertEqual(self.tokens.tenants,[])
        self.assertEqual(self.transport.calls,[])

    def test_post_only_checkmembergroups_approved_group(self):
        uri=GRAPH_ROOT+"/users/"+OID+"/checkMemberGroups"
        with self.assertRaises(ValueError):
            self.http.post_json(uri,{"groupIds":["ffffffff-ffff-4fff-8fff-ffffffffffff"]})
        with self.assertRaises(ValueError):
            self.http.post_json(uri,{"groupIds":[GROUP,OID]})
        with self.assertRaises(ValueError):
            self.http.post_json(uri,{"groupIds":[GROUP],"other":"data"})
        with self.assertRaises(ValueError):
            self.http.post_json(uri+"?override=1",{"groupIds":[GROUP]})
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(self.tokens.tenants,[])

    def test_missing_server_provider_and_transport_fail(self):
        with self.assertRaises(ValueError):
            AotGraphMembershipHttpTransport(tokens=None,transport=self.transport)
        with self.assertRaises(ValueError):
            AotGraphMembershipHttpTransport(tokens=self.tokens,transport=None)
        self.tokens.access_token_for_tenant=lambda **kwargs:None
        with self.assertRaises(PermissionError):
            self.http.get_json(GRAPH_ROOT+"/users/"+OID+"?$select=id,accountEnabled")
        self.assertEqual(self.transport.calls,[])

if __name__=="__main__":
    unittest.main()

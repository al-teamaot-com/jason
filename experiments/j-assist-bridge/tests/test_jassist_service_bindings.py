from __future__ import annotations
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entra_group_screen_authority import EntraGroupEvidence, AOT_JASSIST_PILOT_GROUP_ID
from entra_send_authority import AOT_ENTRA_TENANT_ID
from jassist_service_bindings import prepare_live_bindings, prepare_graph_backed_bindings
from session_gate import Denied, VerifiedTechnician

GROUP=AOT_JASSIST_PILOT_GROUP_ID
OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ALTERNATE="11111111-1111-4111-8111-111111111111"


class ServiceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"jassist.json"
        self.policy={"schema_version":1,"revision":1,"enabled":True,
                     "access_source":"entra_group",
                     "aot_account_uid":"aot-account",
                     "entra_group_id":GROUP,
                     "scope":"screen_assistance",
                     "approval_record":"TEST-APPROVED-NONPROD"}
        self.save()
        self.person=VerifiedTechnician("trusted-tech","aot")
        self.calls=[]
        self.member=True
        self.active=True
        self.oid=OID
        self.evidence_override=None
        self.current_group=GROUP

    def save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.policy))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def read_membership(self,tenant,oid,group):
        self.calls.append(("graph",tenant,oid,group))
        if self.evidence_override is not None:return self.evidence_override
        return EntraGroupEvidence(oid,tenant,group,self.member,
                                  self.active,True)

    def build(self, **changes):
        args={
            "settings_path":self.path,
            "datto_account_uid":"aot-account",
            "identity":lambda ctx:self.person,
            "resolve_entra_user_oid":lambda p:self.oid if p==self.person else None,
            "read_live_membership":self.read_membership,
            "datto_device_in_account":lambda acct,device:
                self.calls.append(("datto",acct,device)) or device=="12345",
        }
        args.update(changes)
        return prepare_live_bindings(**args)

    def test_entra_group_and_native_device_checks_both_required(self):
        gate=self.build()
        receipt,token=gate.start(trusted_context=object(),
                                 device_uid="12345",consent=True)
        gate.authorize_read(trusted_context=object(),
                            session_id=receipt.session_id,token=token,
                            device_uid="12345")
        self.assertEqual(len([x for x in self.calls if x[0]=="graph"]),2)
        self.assertEqual(len([x for x in self.calls if x[0]=="datto"]),2)
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="99999",consent=True)

    def test_no_datto_administrator_level_requirement(self):
        # The runtime binding has no Datto assigned-security-level provider.
        # An enabled Entra member on an approved Datto device is eligible.
        gate=self.build()
        receipt,_=gate.start(trusted_context=object(),
                             device_uid="12345",consent=True)
        self.assertEqual(receipt.device_uid,"12345")

    def test_missing_services_denied(self):
        for field in ("settings_path","datto_account_uid","identity",
                      "resolve_entra_user_oid","read_live_membership",
                      "datto_device_in_account"):
            with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):
                self.build(**{field:None})

    def test_nonmember_disabled_user_or_bad_identity_denied(self):
        gate=self.build()
        for name,value in (("member",False),("active",False),("oid",None)):
            old=getattr(self,name)
            setattr(self,name,value)
            with self.assertRaises(Denied):
                gate.start(trusted_context=object(),device_uid="12345",consent=True)
            setattr(self,name,old)
        self.evidence_override=EntraGroupEvidence(OID,AOT_ENTRA_TENANT_ID,
                                                  ALTERNATE,True,True,True)
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)

    def test_group_and_policy_revocation_during_session(self):
        gate=self.build()
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.member=False
        with self.assertRaises(Denied):
            gate.authorize_read(trusted_context=object(),
                session_id=receipt.session_id,token=token,device_uid="12345")
        self.member=True
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.policy.update(enabled=False,revision=2,approval_record="TEST-REVOKED-NONPROD")
        self.save()
        with self.assertRaises(Denied):
            gate.authorize_read(trusted_context=object(),
                session_id=receipt.session_id,token=token,device_uid="12345")

    def test_group_change_is_configurable_without_redeploy(self):
        gate=self.build()
        self.policy.update(entra_group_id=ALTERNATE,revision=2,
                           approval_record="TEST-ROTATED-NONPROD")
        self.save()
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.assertEqual(self.calls[-2][3],ALTERNATE)
        self.assertEqual(receipt.device_uid,"12345")
        gate.authorize_read(trusted_context=object(),
            session_id=receipt.session_id,token=token,device_uid="12345")

    def test_graph_service_uses_existing_server_token_and_configured_group(self):
        owner=self
        class Tokens:
            def access_token_for_tenant(self,*,microsoft_tenant_id):
                owner.calls.append(("token",microsoft_tenant_id))
                return "synthetic-server-token"
        class Http:
            def request(self,*,method,url,headers,params=None,json=None,timeout_seconds=None):
                owner.calls.append(("http",method,url,dict(json or {})))
                if headers!={"Authorization":"Bearer synthetic-server-token"}:
                    raise AssertionError("not server-only bearer")
                if method=="GET":
                    return {"id":owner.oid,"accountEnabled":owner.active}
                if method=="POST":
                    return {"value":[json["groupIds"][0]] if owner.member else []}
                raise AssertionError("unexpected Graph method")
        gate=prepare_graph_backed_bindings(
            settings_path=self.path,datto_account_uid="aot-account",
            identity=lambda ctx:self.person,
            resolve_entra_user_oid=lambda p:self.oid if p==self.person else None,
            datto_device_in_account=lambda acct,uid:
                acct=="aot-account" and uid=="12345",
            graph_tokens=Tokens(),graph_http=Http())
        receipt,token=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.assertTrue(any(c[0]=="http" and c[1]=="POST"
            and c[3]=={"groupIds":[GROUP]} for c in self.calls))
        self.assertTrue(all(c[1]==AOT_ENTRA_TENANT_ID
            for c in self.calls if c[0]=="token"))

        self.calls.clear()
        self.policy.update(entra_group_id=ALTERNATE,revision=2,
                           approval_record="TEST-GRAPH-ROTATE-NONPROD")
        self.save()
        # Same running gate re-reads the governed group configuration.
        receipt,_=gate.start(trusted_context=object(),device_uid="12345",consent=True)
        self.assertTrue(any(c[0]=="http" and c[1]=="POST"
            and c[3]=={"groupIds":[ALTERNATE]} for c in self.calls))
        self.member=False
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)

    def test_graph_service_fails_closed_without_current_config(self):
        self.policy["enabled"]=False
        self.save()
        class Tokens:
            def access_token_for_tenant(self,**kw):
                raise AssertionError("must not obtain Graph token for disabled policy")
        class Http:
            def request(self,**kw):
                raise AssertionError("must not query Graph for disabled policy")
        gate=prepare_graph_backed_bindings(
            settings_path=self.path,datto_account_uid="aot-account",
            identity=lambda ctx:self.person,
            resolve_entra_user_oid=lambda p:OID,
            datto_device_in_account=lambda a,d:True,
            graph_tokens=Tokens(),graph_http=Http())
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)

    def test_group_policy_rotation_during_graph_check_fails_closed(self):
        original=self.read_membership
        def changing_membership(tenant,oid,group):
            # Concurrent Owner policy update while Graph is in flight.
            result=original(tenant,oid,group)
            self.policy.update(revision=2,entra_group_id=ALTERNATE,
                               approval_record="TEST-RACE-ROTATED-NONPROD")
            self.save()
            return result
        gate=self.build(read_live_membership=changing_membership)
        with self.assertRaises(Denied):
            gate.start(trusted_context=object(),device_uid="12345",consent=True)

    def test_cross_account_and_invalid_policy_denied(self):
        self.policy["aot_account_uid"]="other-account"
        self.save()
        with self.assertRaises(ValueError):self.build()
        self.policy["aot_account_uid"]="aot-account"
        self.policy["entra_group_id"]="bogus"
        self.save()
        with self.assertRaises(ValueError):self.build()


if __name__=="__main__":
    unittest.main()

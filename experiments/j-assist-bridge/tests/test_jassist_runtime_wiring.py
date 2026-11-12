from __future__ import annotations
import base64
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.runtime_wiring import JAssistRuntimeDependencies
from jassist.mcp_image_reader import JAssistMcpImageReader
from jassist.entra_send_authority import (
    AOT_ENTRA_TENANT_ID,JASON_RESOURCE_CLIENT_ID,ENTRA_ISSUER)
from jassist.entra_group_screen_authority import AOT_JASSIST_PILOT_GROUP_ID
from jassist.screen_evidence_intake import AcceptedScreen
from jassist.session_gate import VerifiedTechnician,Denied
from jassist.jassist_evidence_api import JAssistApiDenied

OID="22222222-2222-4222-8222-222222222222"
SPA="d1cc801b-13ba-4d44-bea6-e7f08186e4d5"
JPEG=bytes.fromhex("ffd8ffe000104a46494600")+b"synthetic isolated test"+bytes.fromhex("ffd9")

class Tokens:
    def access_token_for_tenant(self,*,microsoft_tenant_id):
        if microsoft_tenant_id!=AOT_ENTRA_TENANT_ID:raise PermissionError()
        return "synthetic-server-only-graph-token"

class Transport:
    def __init__(self,scope):self.scope=scope;self.member=True
    def request(self,*,method,url,headers,params=None,json=None,timeout_seconds=10.0):
        if headers.get("Authorization")!="Bearer synthetic-server-only-graph-token":
            raise PermissionError()
        if method=="GET":return {"id":OID,"accountEnabled":True}
        if method=="POST":
            if json!={"groupIds":[self.scope]}:raise PermissionError()
            return {"value":[self.scope] if self.member else []}
        raise AssertionError("Unexpected request")


class RuntimeWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.policy_path=root/"policy.json"
        self.policy={"schema_version":1,"revision":1,"enabled":True,
            "access_source":"entra_group","aot_account_uid":"AOT-TEST",
            "entra_group_id":AOT_JASSIST_PILOT_GROUP_ID,
            "scope":"screen_assistance",
            "approval_record":"TEST-RUNTIME-WIRING-NONPRODUCTION"}
        self.publish()
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.person=VerifiedTechnician("synthetic-person","aot")
        self.graph=Transport(AOT_JASSIST_PILOT_GROUP_ID)
        self.review_ready=True
        self.tls_ready=True
        self.deps=JAssistRuntimeDependencies(
            policy_path=self.policy_path,
            session_db_path=root/"sessions.db",evidence_db_path=root/"images.db",
            aot_datto_account_uid="AOT-TEST",entra_spa_client_id=SPA,
            identity_for_context=lambda ctx:ctx,
            resolve_entra_user_oid=lambda who:OID if who==self.person else None,
            resolve_active_aot_identity=lambda tid,oid:
                self.person if tid==AOT_ENTRA_TENANT_ID and oid==OID else None,
            entra_signing_key_for=lambda bearer:self.key.public_key(),
            graph_tokens=Tokens(),graph_transport=self.graph,
            datto_device_in_account=lambda account,device:
                account=="AOT-TEST" and device=="1717088",
            session_encryption_key=b"s"*32,evidence_encryption_key=b"e"*32,
            content_reviewer=lambda data:AcceptedScreen(data,"synthetic-review","test"),
            content_review_ready=lambda:self.review_ready,
            secure_ingress_ready=lambda:self.tls_ready,
        )
        self.running=self.deps.build()

    def publish(self):
        tmp=self.policy_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.policy));tmp.chmod(0o600)
        tmp.replace(self.policy_path)

    def bearer(self,**replace):
        now=int(time.time())
        claims={"iss":ENTRA_ISSUER,"aud":JASON_RESOURCE_CLIENT_ID,
                "tid":AOT_ENTRA_TENANT_ID,"oid":OID,"azp":SPA,"scp":"JAssist.Send",
                "iat":now-10,"nbf":now-10,"exp":now+3600}
        claims.update(replace)
        return jwt.encode(claims,self.key,algorithm="RS256",headers={"kid":"synthetic"})

    def test_real_jwt_graph_device_durable_session_encrypted_evidence_and_mcp(self):
        bearer=self.bearer()
        ready=self.running.api.readiness(bearer=bearer,device_uid="1717088")
        self.assertEqual(ready["status"],"ready")
        session=self.running.api.create_session(bearer=bearer,
                   device_uid="1717088",consent=True)
        self.assertNotIn("secret",session)
        self.assertNotIn("token",session)
        sid=session["session_id"]
        receipt=self.running.api.accept_image(
            bearer=bearer,session_id=sid,device_uid="1717088",
            nonce="TestNonceRuntimeABC123",image=JPEG,
            sha256=hashlib.sha256(JPEG).hexdigest())
        mcp=self.running.mcp_image_tool.read_reviewed_image(
            authenticated_technician=self.person,
            session_id=sid,device_uid="1717088",receipt_id=receipt["receipt_id"])
        self.assertEqual(base64.b64decode(mcp["image"]["data"]),JPEG)
        # Both secrets and image survive restart without storing plaintext.
        rebuilt=self.deps.build()
        observed=rebuilt.mcp_image_tool.read_reviewed_image(
            authenticated_technician=self.person,session_id=sid,
            device_uid="1717088",receipt_id=receipt["receipt_id"])
        self.assertEqual(base64.b64decode(observed["image"]["data"]),JPEG)
        self.assertNotIn(JPEG,self.deps.evidence_db_path.read_bytes())

    def test_mcp_receipt_is_individually_authorized_with_existing_jason_identity(self):
        bearer=self.bearer()
        session=self.running.api.create_session(
            bearer=bearer,device_uid="1717088",consent=True)
        receipt=self.running.api.accept_image(
            bearer=bearer,session_id=session["session_id"],
            device_uid="1717088",nonce="TestMcpNonceXYZ1234",image=JPEG,
            sha256=hashlib.sha256(JPEG).hexdigest())
        reader=JAssistMcpImageReader(
            reviewed_image_tool=self.running.mcp_image_tool,
            resolve_authenticated_mcp_identity=lambda:(
                self.person.subject,self.person.tenant_id,
                "entra-oauth-bearer",None),
            image_read_enabled=lambda:True)
        output=reader.read(session_id=session["session_id"],
               device_uid="1717088",receipt_id=receipt["receipt_id"])
        self.assertEqual(output["status"],"succeeded")
        self.assertEqual(base64.b64decode(output["content"][1]["data"]),JPEG)
        denied=JAssistMcpImageReader(
            reviewed_image_tool=self.running.mcp_image_tool,
            resolve_authenticated_mcp_identity=lambda:(
                "other-person","aot","entra-oauth-bearer",None),
            image_read_enabled=lambda:True)
        with self.assertRaises(Denied):
            denied.read(session_id=session["session_id"],
              device_uid="1717088",receipt_id=receipt["receipt_id"])
        disabled=JAssistMcpImageReader(
            reviewed_image_tool=self.running.mcp_image_tool,
            resolve_authenticated_mcp_identity=lambda:(
                self.person.subject,"aot","entra-oauth-bearer",None),
            image_read_enabled=lambda:False)
        with self.assertRaises(Denied):
            disabled.read(session_id=session["session_id"],
                device_uid="1717088",receipt_id=receipt["receipt_id"])

    def test_auth_scope_group_and_tls_outage_fail_closed(self):
        for claims in ({"scp":"Jason.Read"},{"azp":OID},{"tid":OID}):
            with self.subTest(claims=claims),self.assertRaises(JAssistApiDenied):
                self.running.api.readiness(bearer=self.bearer(**claims),
                    device_uid="1717088")
        self.graph.member=False
        with self.assertRaises(JAssistApiDenied):
            self.running.api.readiness(bearer=self.bearer(),device_uid="1717088")
        self.graph.member=True
        self.tls_ready=False
        with self.assertRaises(JAssistApiDenied) as err:
            self.running.api.readiness(bearer=self.bearer(),device_uid="1717088")
        self.assertEqual(err.exception.code,503)

    def test_no_access_if_policy_disabled_or_key_shared(self):
        self.policy["enabled"]=False
        self.policy["revision"]=2
        self.policy["approval_record"]="TEST-RUNTIME-DISABLED-REVISION"
        self.publish()
        with self.assertRaises(JAssistApiDenied):
            self.running.api.readiness(bearer=self.bearer(),device_uid="1717088")
        with self.assertRaises(ValueError):
            from dataclasses import replace
            replace(self.deps,evidence_encryption_key=b"s"*32).build()


if __name__=="__main__":unittest.main()

"""Full synthetic (nonproduction) pilot composition and relay-to-MCP lifecycle."""
from __future__ import annotations
import asyncio
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

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.entra_send_authority import (
    AOT_ENTRA_TENANT_ID,ENTRA_ISSUER,JASON_RESOURCE_CLIENT_ID)
from jassist.jassist_asgi_gateway import APPROVED_CHROME_ORIGIN
from jassist.governed_aes_keys import GovernedJAssistKeyBroker
from jassist.pilot_runtime_composition import (
    JAssistPilotRuntimeFactory,PilotExactActionAttestation)
from jassist.session_gate import Denied,VerifiedTechnician

OID="22222222-2222-4222-8222-222222222222"
GROUP="5273dd8a-1456-4985-b0a3-c00061267e26"
SPA="d1cc801b-13ba-4d44-bea6-e7f08186e4d5"
SITE="9bb56523-cade-4ffb-bc34-696e788f0f4c"
UID="1717088"
NATIVE="710e63d6-caca-d830-697a-81250b0a8321"
JPEG=bytes.fromhex("ffd8ffe000104a46494600")+b"synthetic AOT review fixture"+bytes.fromhex("ffd9")

class Tokens:
    def access_token_for_tenant(self,*,microsoft_tenant_id):
        if microsoft_tenant_id!=AOT_ENTRA_TENANT_ID:
            raise PermissionError("not verified AOT tenant")
        return "synthetic-server-only-graph-token"

class Graph:
    def __init__(self):
        self.member=True
        self.calls=[]
    def request(self,*,method,url,headers,params=None,json=None,timeout_seconds=10.0):
        self.calls.append((method,url))
        if headers.get("Authorization")!="Bearer synthetic-server-only-graph-token":
            raise PermissionError("unknown Graph authority")
        if method=="GET":
            return {"id":OID,"accountEnabled":True}
        if method=="POST":
            if json!={"groupIds":[GROUP]}:
                raise PermissionError("unexpected group")
            return {"value":[GROUP] if self.member else []}
        raise AssertionError("unapproved Graph method")

class PilotLiveCompositionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.person=VerifiedTechnician("synthetic-aot-technician","aot")
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.graph=Graph()
        self.mapped_id=True
        self.https=True
        self.review_attested=True
        self.release_attested=True
        policy={"schema_version":1,"revision":1,"enabled":True,
                "access_source":"entra_group","aot_account_uid":SITE,
                "entra_group_id":GROUP,"scope":"screen_assistance",
                "approval_record":"TEST-PILOT-EXACT-AOT-OWNER"}
        self.policy=self.root/"group.json"
        self.policy.write_text(json.dumps(policy));self.policy.chmod(0o600)
        review={"schema_version":1,"enabled":True,
                "policy_version":"AOT-PILOT-REVIEW-001",
                "reviewer_id":"AOT-OWNER-REVIEWER",
                "approved_sha256":[hashlib.sha256(JPEG).hexdigest()]}
        self.review=self.root/"review.json"
        self.review.write_text(json.dumps(review,sort_keys=True))
        self.review.chmod(0o600)
        self.review_sha=hashlib.sha256(self.review.read_bytes()).hexdigest()
        keys={"jassist.session_encryption":
                   {"key_b64":base64.b64encode(b"s"*32).decode()},
              "jassist.evidence_encryption":
                   {"key_b64":base64.b64encode(b"e"*32).decode()}}
        self.restriction=PilotExactActionAttestation(
            candidate_sha="a"*40,
            reviewed_scope_sha256="b"*64,
            relay_readback_sha256="c"*64,
            aot_test_device_uid=UID,
            owner_approval_reference="OWNER-AOT-PILOT-VERIFIED",
            production_deployment_authorized=False)
        self.datto_calls=[]
        def datto(uid):
            self.datto_calls.append(uid)
            if not self.mapped_id:
                raise PermissionError("Datto proof revoked")
            return {"status":"succeeded","stage":"completed",
                    "capability":"endpoint.device.read","provider":"datto_rmm",
                    "evidence":{"provider":"datto_rmm",
                        "provider_capability":"datto_rmm.device.get",
                        "record":{"resource_id":NATIVE,"provider_device_id":1717088,
                                  "site_id":SITE,"hostname":"Al-Samsung",
                                  "online":True,"suspended":False,
                                  "deleted":False}}}
        self.factory=JAssistPilotRuntimeFactory(
            policy_path=self.policy,
            review_policy_path=self.review,
            session_db_path=self.root/"sessions.db",
            evidence_db_path=self.root/"images.db",
            pinned_aot_site_uid=SITE,
            approved_spa_client_id=SPA,
            graph_tokens=Tokens(),graph_transport=self.graph,
            governed_datto_device_read=datto,
            identity_for_context=lambda x:x,
            resolve_entra_user_oid=lambda person:
                OID if person==self.person else None,
            resolve_active_aot_identity=lambda tid,oid:
                self.person if tid==AOT_ENTRA_TENANT_ID and oid==OID else None,
            encryption_keys=GovernedJAssistKeyBroker(resolve=keys.__getitem__),
            verify_exact_pilot_action=lambda att:
                self.release_attested and att==self.restriction,
            verify_review_manifest_sha256=lambda digest:
                self.review_attested and digest==self.review_sha,
            secure_ingress_ready=lambda:self.https,
            jwks=lambda token:self.key.public_key(),
        )

    def token(self):
        n=int(time.time())
        return jwt.encode(
            {"iss":ENTRA_ISSUER,"aud":JASON_RESOURCE_CLIENT_ID,
             "tid":AOT_ENTRA_TENANT_ID,"oid":OID,"azp":SPA,
             "scp":"JAssist.Send","iat":n-2,"nbf":n-2,"exp":n+600},
            self.key,algorithm="RS256",headers={"kid":"fixture-key"})

    def call(self,app,method,path,body=None,headers=None,peer="10.87.246.16"):
        extra={"origin":APPROVED_CHROME_ORIGIN,
               "host":"mcp-jason.teamaot.com",
               "x-forwarded-host":"mcp-jason.teamaot.com",
               "x-forwarded-proto":"https",
               "authorization":"Bearer "+self.token()}
        if headers:extra.update(headers)
        if body is None:payload=b""
        elif isinstance(body,bytes):payload=body
        else:
            payload=json.dumps(body).encode()
            extra["content-type"]="application/json"
        scope={"type":"http","method":method,"scheme":"http",
               "client":(peer,51888),"path":path.split("?")[0],
               "query_string":path.split("?",1)[1].encode()
                         if "?" in path else b"",
               "headers":[(k.encode(),v.encode()) for k,v in extra.items()]}
        events=[]
        async def receive():
            return {"type":"http.request","body":payload,"more_body":False}
        async def send(message):
            events.append(message)
        asyncio.run(app(scope,receive,send))
        return events[0]["status"],json.loads(events[1]["body"])

    def test_approved_browser_to_reviewed_encrypted_mcp_and_revocation(self):
        service=self.factory.build(self.restriction)
        ingress=service.ingress
        status,ready=self.call(
            ingress,"GET","/v1/jassist/readiness?device_uid="+UID)
        self.assertEqual(status,200)
        self.assertTrue(ready["entra_group_verified"])
        self.assertTrue(ready["datto_device_authorized"])
        status,session=self.call(
            ingress,"POST","/v1/jassist/session",
            {"device_uid":UID,"consent":True})
        self.assertEqual(status,201)
        sid=session["session_id"]
        status,receipt=self.call(
            ingress,"POST","/v1/jassist/image",JPEG,headers={
              "content-type":"image/jpeg",
              "x-jassist-session":sid,
              "x-jassist-device":UID,
              "x-jassist-sha256":hashlib.sha256(JPEG).hexdigest(),
              "x-jassist-nonce":"SyntheticBrowserNonceABC1234"})
        self.assertEqual(status,201)
        self.assertEqual(receipt["status"],"accepted")
        self.assertFalse(receipt["analyzed_by_model"])
        content=service.components.mcp_image_tool.read_reviewed_image(
            authenticated_technician=self.person,
            session_id=sid,device_uid=UID,receipt_id=receipt["receipt_id"])
        self.assertEqual(base64.b64decode(content["image"]["data"]),JPEG)
        self.assertNotIn(JPEG,self.factory.evidence_db_path.read_bytes())
        self.assertGreaterEqual(len(self.datto_calls),4)
        self.assertGreaterEqual(len(self.graph.calls),8)
        # Live member removal denies the same previously accepted frame.
        self.graph.member=False
        with self.assertRaises(Denied):
            service.components.mcp_image_tool.read_reviewed_image(
                authenticated_technician=self.person,session_id=sid,
                device_uid=UID,receipt_id=receipt["receipt_id"])

    def test_unreviewed_screen_denied_and_wrong_device_blocked(self):
        service=self.factory.build(self.restriction)
        status,body=self.call(service.ingress,"GET",
              "/v1/jassist/readiness?device_uid=99999")
        self.assertEqual(status,403)
        sid=self.call(service.ingress,"POST","/v1/jassist/session",
             {"device_uid":UID,"consent":True})[1]["session_id"]
        changed=JPEG+b"sensitive content"
        status,body=self.call(
            service.ingress,"POST","/v1/jassist/image",changed,headers={
              "content-type":"image/jpeg",
              "x-jassist-session":sid,"x-jassist-device":UID,
              "x-jassist-sha256":hashlib.sha256(changed).hexdigest(),
              "x-jassist-nonce":"SyntheticBrowserNonceDEF1234"})
        self.assertEqual(status,403)
        self.assertEqual(body["status"],"error")

    def test_absent_review_https_or_owner_authority_does_not_create_state(self):
        for flag in ("release_attested","review_attested","https"):
            with self.subTest(flag=flag):
                setattr(self,flag,False)
                with self.assertRaises(PermissionError):
                    self.factory.build(self.restriction)
                self.assertFalse(self.factory.session_db_path.exists())
                self.assertFalse(self.factory.evidence_db_path.exists())
                setattr(self,flag,True)
        policy=json.loads(self.policy.read_text())
        policy["enabled"]=False
        self.policy.write_text(json.dumps(policy))
        with self.assertRaises(PermissionError):
            self.factory.build(self.restriction)
        self.assertFalse(self.factory.session_db_path.exists())
        policy["enabled"]=True
        self.policy.write_text(json.dumps(policy))
        from dataclasses import replace
        with self.assertRaises(PermissionError):
            self.factory.build(replace(self.restriction,
                production_deployment_authorized=True))
        with self.assertRaises(PermissionError):
            self.factory.build(replace(self.restriction,
                aot_test_device_uid="9999"))

if __name__=="__main__":unittest.main()

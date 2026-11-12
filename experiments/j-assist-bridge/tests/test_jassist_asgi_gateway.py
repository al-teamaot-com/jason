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

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jassist_durable_sessions import DurableJAssistSessionGate
from jassist_encrypted_evidence import EncryptedJAssistEvidenceIntake
from jassist_evidence_api import JAssistEvidenceApi
from jassist_asgi_gateway import JAssistASGIGateway, APPROVED_CHROME_ORIGIN
from screen_evidence_intake import AcceptedScreen
from chatgpt_image_tool import ChatGPTImageEvidenceTool
from session_gate import VerifiedTechnician,Denied

JPEG=bytes.fromhex("ffd8ffe000104a46494600")+b"synthetic JAssist E2E"+bytes.fromhex("ffd9")
BEARER="a"*512
DEVICE="1717088"


class AsgiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.person=VerifiedTechnician("synthetic-aot-oid","aot")
        self.is_member=True
        self.review_ready=True
        self.ingress_ready=True
        self.gate=DurableJAssistSessionGate(
            db_path=root/"sessions.db",encryption_key=b"s"*32,
            identity=lambda p:p,can_read_datto_device=lambda person,uid:
                self.is_member and person==self.person and uid==DEVICE)
        self.intake=EncryptedJAssistEvidenceIntake(
            db_path=root/"images.db",encryption_key=b"i"*32,
            gate=self.gate,review_content=lambda data:
                AcceptedScreen(data,"synthetic-reviewer","test-fixture"))
        self.api=JAssistEvidenceApi(
            authenticate_bearer=lambda bearer:
                self.person if bearer==BEARER else None,
            durable_gate=self.gate,encrypted_intake=self.intake,
            content_review_ready=lambda:self.review_ready,
            secure_ingress_ready=lambda:self.ingress_ready)
        self.gateway=JAssistASGIGateway(api=self.api)
        self.mcp=ChatGPTImageEvidenceTool(
            intake=self.intake,credential_lookup=self.gate.credential_for)

    def request(self,method,path,body=b"",scheme="https",headers=None):
        if not isinstance(body,bytes):
            body=json.dumps(body).encode()
        pairs={"origin":APPROVED_CHROME_ORIGIN,
               "authorization":"Bearer "+BEARER}
        if method=="POST":pairs["content-type"]="application/json"
        pairs.update(headers or {})
        scope={"type":"http","method":method,
               "scheme":scheme,
               "path":path.split("?")[0],
               "query_string":path.split("?",1)[1].encode() if "?" in path else b"",
               "headers":[(k.encode(),v.encode()) for k,v in pairs.items()]}
        events=[]
        async def receive():
            return {"type":"http.request","body":body,"more_body":False}
        async def send(event):
            events.append(event)
        asyncio.run(self.gateway(scope,receive,send))
        status=events[0]["status"]
        output=events[1]["body"]
        response_headers={k.decode():v.decode() for k,v in events[0]["headers"]}
        return status,json.loads(output) if output else None,response_headers

    def create(self):
        return self.request("POST","/v1/jassist/session",
                            {"device_uid":DEVICE,"consent":True})

    def send_image(self,session,nonce="BrowserNonceSynthetic123"):
        return self.request("POST","/v1/jassist/image",JPEG,headers={
            "content-type":"image/jpeg","x-jassist-session":session,
            "x-jassist-device":DEVICE,
            "x-jassist-sha256":hashlib.sha256(JPEG).hexdigest(),
            "x-jassist-nonce":nonce})

    def test_browser_compatible_asgi_session_upload_and_mcp_read(self):
        status,ready,headers=self.request("GET","/v1/jassist/readiness?device_uid="+DEVICE)
        self.assertEqual(status,200)
        self.assertTrue(ready["entra_group_verified"])
        self.assertTrue(ready["image_review_ready"])
        self.assertEqual(headers["access-control-allow-origin"],APPROVED_CHROME_ORIGIN)
        status,session,headers=self.create()
        self.assertEqual(status,201)
        self.assertNotIn("token",session)
        self.assertNotIn("secret",session)
        sid=session["session_id"]
        status,valid,_=self.request("POST","/v1/jassist/session/validate",
                                  {"session_id":sid,"device_uid":DEVICE})
        self.assertEqual(status,200)
        self.assertEqual(valid["status"],"authorized")
        status,receipt,_=self.send_image(sid)
        self.assertEqual(status,201)
        self.assertEqual(receipt["status"],"accepted")
        self.assertFalse(receipt["analyzed_by_model"])
        read=self.mcp.read_reviewed_image(
            authenticated_technician=self.person,
            session_id=sid,device_uid=DEVICE,receipt_id=receipt["receipt_id"])
        self.assertEqual(base64.b64decode(read["image"]["data"]),JPEG)
        self.assertEqual(self.send_image(sid)[0],403)
        status,_,_=self.request("POST","/v1/jassist/session/stop",
                    {"session_id":sid,"device_uid":DEVICE})
        self.assertEqual(status,200)
        with self.assertRaises(Denied):
            self.mcp.read_reviewed_image(
                authenticated_technician=self.person,
                session_id=sid,device_uid=DEVICE,
                receipt_id=receipt["receipt_id"])

    def test_invalid_origin_tls_and_auth_never_offer_upload(self):
        for args in [
            {"scheme":"http"},
            {"headers":{"origin":"https://evil.test"}},
            {"headers":{"authorization":"Bearer "+"z"*512}},
        ]:
            status,body,_=self.request(
                "GET","/v1/jassist/readiness?device_uid="+DEVICE,**args)
            self.assertNotEqual(status,200)
            self.assertNotEqual(body.get("status"),"ready")
        self.assertEqual(self.request("OPTIONS","/v1/jassist/image",
            headers={"access-control-request-headers":"authorization,x-jassist-session-token"})[0],403)

    def test_duplicate_consent_field_fails_closed(self):
        status,body,_=self.request("POST","/v1/jassist/session",
            b'{"device_uid":"1717088","consent":false,"consent":true}')
        self.assertEqual(status,400)
        self.assertEqual(body["status"],"error")

    def test_review_service_missing_and_disabled_group(self):
        self.review_ready=False
        self.assertEqual(self.create()[0],503)
        self.review_ready=True
        self.is_member=False
        self.assertEqual(self.create()[0],403)
        self.is_member=True
        status,session,_=self.create()
        self.assertEqual(status,201)
        self.is_member=False
        self.assertEqual(self.send_image(session["session_id"])[0],403)

    def test_oversize_unsafe_envelope_and_no_client_secret_header(self):
        sid=self.create()[1]["session_id"]
        status,_,_=self.request("POST","/v1/jassist/image",JPEG,
          headers={"content-type":"image/jpeg","x-jassist-session":sid,
            "x-jassist-device":DEVICE,"x-jassist-sha256":"a"*64,
            "x-jassist-nonce":"BrowserNonceSynthetic456"})
        self.assertEqual(status,403)
        status,_,_=self.request("POST","/v1/jassist/image",JPEG,
          headers={"content-type":"image/jpeg","x-jassist-session":sid,
            "x-jassist-device":DEVICE,"x-jassist-sha256":hashlib.sha256(JPEG).hexdigest(),
            "x-jassist-nonce":"BrowserNonceSynthetic456",
            "x-jassist-session-token":"forbidden"})
        self.assertEqual(status,403)
        self.assertEqual(self.request("POST","/v1/jassist/session",
           {"device_uid":DEVICE,"consent":False})[0],403)
        self.assertEqual(self.request("POST","/v1/jassist/session",
           {"device_uid":DEVICE,"consent":True,"admin":True})[0],400)


if __name__=="__main__":unittest.main()

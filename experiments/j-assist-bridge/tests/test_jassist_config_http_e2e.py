from __future__ import annotations
import hashlib, json, http.client, sys, tempfile, threading, time, unittest, base64
from pathlib import Path
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jassist_service_bindings import prepare_live_bindings
from entra_group_screen_authority import EntraGroupEvidence, AOT_JASSIST_PILOT_GROUP_ID
from entra_send_authority import AOT_ENTRA_TENANT_ID, JASON_RESOURCE_CLIENT_ID, ENTRA_ISSUER, EntraSendAuthority
from session_gate import VerifiedTechnician, Denied
from loopback_transport import create_loopback_server
from screen_evidence_intake import AcceptedScreen, ScreenEvidenceIntake
from chatgpt_image_tool import ChatGPTImageEvidenceTool
from synthetic_probe import SyntheticProbe

# Real localhost HTTP, but synthetic identities, JWT, screenshot, membership and DLP.
# NOT a production or Datto-connected end-to-end test.
class ConfigBoundLoopbackE2E(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"policy.json"
        self.policy={"schema_version":1,"revision":1,"enabled":True,
            "access_source":"entra_group",
            "aot_account_uid":"synthetic-aot","entra_group_id":AOT_JASSIST_PILOT_GROUP_ID,
            "scope":"screen_assistance","approval_record":"TEST-ONLY-NO-APPROVAL"}
        self.publish()
        self.person=VerifiedTechnician("test-tech","aot")
        self.is_member=True
        self.oid="22222222-2222-2222-2222-222222222222"
        self.gate=prepare_live_bindings(settings_path=self.path,
            datto_account_uid="synthetic-aot",identity=lambda ctx:ctx,
            resolve_entra_user_oid=lambda p:self.oid if p==self.person else None,
            read_live_membership=lambda t,oid,group:
                EntraGroupEvidence(oid,t,group,self.is_member,True,True),
            datto_device_in_account=lambda a,d:a=="synthetic-aot" and d=="12345")
        self.session,self.secret=self.gate.start(trusted_context=self.person,
            device_uid="12345",consent=True)
        self.image=bytes.fromhex("ffd8ffe000104a46494600")+b"safe synthetic image"+bytes.fromhex("ffd9")
        self.intake=ScreenEvidenceIntake(gate=self.gate,
            review_content=lambda data:AcceptedScreen(data,"synthetic-review","test"))
        self.image_tool=ChatGPTImageEvidenceTool(intake=self.intake,
            credential_lookup=lambda sid:self.secret if sid==self.session.session_id else None)
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.spa="87654321-4321-4321-4321-abcdefabcdef"
        self.oid="22222222-2222-2222-2222-222222222222"
        auth=EntraSendAuthority(allowed_spa_client_id=self.spa,
            signing_key_for=lambda t:self.key.public_key(),
            resolve_active_aot_identity=lambda t,o:self.person
            if t==AOT_ENTRA_TENANT_ID and o==self.oid else None)
        self.server=create_loopback_server(probe=SyntheticProbe(self.gate),
            authenticate=auth.authenticate,image_intake=self.intake,
            session_credential_for=lambda user,sid:self.secret
            if user==self.person and sid==self.session.session_id else None)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
        self.temp.cleanup()
    def publish(self):
        tmp=self.path.with_suffix(".tmp");tmp.write_text(json.dumps(self.policy))
        tmp.chmod(0o600);tmp.replace(self.path)
    def send(self,nonce):
        now=int(time.time())
        token=jwt.encode({"iss":ENTRA_ISSUER,"aud":JASON_RESOURCE_CLIENT_ID,
            "tid":AOT_ENTRA_TENANT_ID,"oid":self.oid,"scp":"JAssist.Send",
            "azp":self.spa,"iat":now-10,"nbf":now-10,"exp":now+3600},
            self.key,algorithm="RS256",headers={"kid":"synthetic-test"})
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_address[1],timeout=3)
        conn.request("POST","/v1/jassist/image",self.image,
            {"Authorization":"Bearer "+token,"Content-Type":"image/jpeg",
             "X-JAssist-Session":self.session.session_id,"X-JAssist-Device":"12345",
             "X-JAssist-Nonce":nonce,"X-JAssist-SHA256":hashlib.sha256(self.image).hexdigest()})
        reply=conn.getresponse();result=reply.status,reply.read();conn.close()
        return result
    def test_http_receipt_mcp_retrieval_and_replay(self):
        code,body=self.send("SyntheticNonceForE2E123")
        self.assertEqual(code,201)
        receipt=json.loads(body)
        result=self.image_tool.read_reviewed_image(authenticated_technician=self.person,
            session_id=self.session.session_id,device_uid="12345",
            receipt_id=receipt["receipt_id"])
        self.assertEqual(base64.b64decode(result["image"]["data"]),self.image)
        self.assertFalse(result["production_connected"])
        self.assertFalse(receipt["production_ingress"])
        self.assertEqual(self.send("SyntheticNonceForE2E123")[0],403)
    def test_config_revocation_denies_upload_and_mcp_read(self):
        code,body=self.send("SyntheticNonceForE2E456")
        self.assertEqual(code,201)
        receipt=json.loads(body)
        self.policy.update(enabled=False,revision=2,approval_record="TEST-REVOCATION-ONLY")
        self.publish()
        self.assertEqual(self.send("SyntheticNonceForE2E789")[0],403)
        with self.assertRaises(Denied):
            self.image_tool.read_reviewed_image(authenticated_technician=self.person,
                session_id=self.session.session_id,device_uid="12345",
                receipt_id=receipt["receipt_id"])
    def test_entra_membership_revocation_denies_send(self):
        self.is_member=False
        self.assertEqual(self.send("SyntheticNonceForE2E999")[0],403)

if __name__=="__main__":unittest.main()

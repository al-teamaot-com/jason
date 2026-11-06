from __future__ import annotations
import hashlib
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from loopback_transport import create_loopback_server
from screen_evidence_intake import AcceptedScreen, ScreenEvidenceIntake
from session_gate import SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe

FRAME=bytes.fromhex("89504e470d0a1a0a")+b"synthetic-test-image-only"


class ImageHttpTransportTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.permissions={("staff-a","1717088")}
        self.user=VerifiedTechnician("staff-a","aot")
        self.gate=SessionGate(identity=lambda value:value,
            can_read_datto_device=lambda p,d:(p.subject,d) in self.permissions,
            clock=lambda:self.now)
        self.session,self.token=self.gate.start(
            trusted_context=self.user,device_uid="1717088",consent=True)
        self.intake=ScreenEvidenceIntake(gate=self.gate,
            review_content=lambda img:AcceptedScreen(img,"offline-test-reviewer","synthetic-v1"),
            clock=lambda:self.now)
        self.identities={"test-bearer":self.user}
        self.server=create_loopback_server(probe=SyntheticProbe(self.gate),
            authenticate=self.identities.get,image_intake=self.intake)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def send(self, *, bearer="test-bearer",body=FRAME,headers=None,path="/v1/test-image"):
        values={
            "Authorization":"Bearer "+bearer,
            "Content-Type":"image/png",
            "X-JAssist-Session":self.session.session_id,
            "X-JAssist-Session-Token":self.token,
            "X-JAssist-Device":"1717088",
            "X-JAssist-Nonce":"UniqueImageRequest123",
            "X-JAssist-SHA256":hashlib.sha256(body).hexdigest(),
        }
        values.update(headers or {})
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_address[1],timeout=3)
        conn.request("POST",path,body,values)
        res=conn.getresponse()
        status,payload=res.status,res.read()
        conn.close()
        return status,payload

    def test_actual_http_image_bytes_and_acknowledgement(self):
        status,body=self.send()
        self.assertEqual(status,201)
        receipt=json.loads(body)
        self.assertEqual(receipt["image_sha256"],hashlib.sha256(FRAME).hexdigest())
        self.assertFalse(receipt["production_ingress"])
        self.assertFalse(receipt["analyzed_by_model"])
        self.assertNotIn(self.token,body.decode())
        self.assertEqual(self.server.server_address[0],"127.0.0.1")

    def test_no_auth_wrong_hash_replay_device_and_revocation(self):
        self.assertEqual(self.send(bearer="unknown")[0],401)
        self.assertEqual(self.send(headers={"X-JAssist-SHA256":"a"*64})[0],403)
        self.assertEqual(self.send(headers={"X-JAssist-Device":"9"})[0],403)
        self.assertEqual(self.send()[0],201)
        self.assertEqual(self.send()[0],403)
        self.permissions.clear()
        self.assertEqual(self.send(headers={"X-JAssist-Nonce":"UniqueImageRequest456"})[0],403)

    def test_wrong_mime_or_bad_image(self):
        self.assertEqual(self.send(headers={"Content-Type":"application/json"})[0],415)
        self.assertEqual(self.send(body=b"untrusted")[0],403)

    def test_no_default_image_reviewer_means_404(self):
        other=create_loopback_server(probe=SyntheticProbe(self.gate),authenticate=self.identities.get)
        worker=threading.Thread(target=other.serve_forever,daemon=True)
        worker.start()
        try:
            conn=http.client.HTTPConnection("127.0.0.1",other.server_address[1],timeout=3)
            conn.request("POST","/v1/test-image",FRAME,{"Content-Type":"image/png"})
            res=conn.getresponse()
            self.assertEqual(res.status,404)
            res.read()
            conn.close()
        finally:
            other.shutdown();other.server_close();worker.join(timeout=3)


if __name__=="__main__":
    unittest.main()

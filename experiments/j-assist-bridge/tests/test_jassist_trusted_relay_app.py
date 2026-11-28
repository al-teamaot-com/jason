"""Direct/forged traffic cannot assert the TLS-terminated Caddy scope."""
from __future__ import annotations
import asyncio
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.jassist_evidence_api import JAssistEvidenceApi
from jassist.jassist_asgi_gateway import JAssistASGIGateway,APPROVED_CHROME_ORIGIN
from jassist.trusted_relay_app import TrustedCaddyJAssistIngress

class RelayIngressTests(unittest.TestCase):
    def setUp(self):
        api=JAssistEvidenceApi.__new__(JAssistEvidenceApi)
        api.readiness=lambda **kwargs:{"status":"ready",
            "device_uid":kwargs["device_uid"],
            "technician_verified":True,
            "entra_group_verified":True,
            "datto_device_authorized":True,
            "image_review_ready":True,
            "production_ingress":True}
        self.app=TrustedCaddyJAssistIngress(gateway=JAssistASGIGateway(api=api))

    def invoke(self, *, peer="10.87.246.16", scheme="http", method="GET",
               path="/v1/jassist/readiness", headers=None):
        request_headers={
            "origin":APPROVED_CHROME_ORIGIN,
            "host":"mcp-jason.teamaot.com",
            "x-forwarded-proto":"https",
            "x-forwarded-host":"mcp-jason.teamaot.com",
            "authorization":"Bearer "+("a"*512),
        }
        if headers is not None:request_headers.update(headers)
        scope={"type":"http","path":path,"method":method,"scheme":scheme,
               "query_string":b"device_uid=1717088",
               "client":(peer,3244),
               "headers":[(k.encode(),v.encode()) for k,v in request_headers.items()]}
        events=[]
        async def recv():return {"type":"http.request","body":b"","more_body":False}
        async def send(ev):events.append(ev)
        asyncio.run(self.app(scope,recv,send))
        status=events[0]["status"]
        return status,json.loads(events[1]["body"])

    def test_exact_aws_zerotier_caddy_tls_proof_reaches_the_api(self):
        status,body=self.invoke()
        self.assertEqual(status,200)
        self.assertEqual(body["device_uid"],"1717088")

    def test_spoofed_https_headers_wrong_peer_or_host_fail(self):
        for kw in (
            {"peer":"127.0.0.1"},{"peer":"10.87.246.42"},
            {"scheme":"https"},{"headers":{"x-forwarded-proto":"http"}},
            {"headers":{"host":"attacker.example"}},
            {"headers":{"x-forwarded-host":"attacker.example"}},
            {"headers":{"origin":"https://attacker.example"}},
        ):
            with self.subTest(kw=kw):
                status,body=self.invoke(**kw)
                if kw.get("headers",{}).get("origin")=="https://attacker.example":
                    self.assertEqual(status,403)
                else:self.assertEqual(status,403)
        status,body=self.invoke(peer="10.87.246.16",
                               headers={"x-forwarded-proto":"https,http"})
        self.assertEqual(status,403)

    def test_health_never_signals_upload_authority(self):
        status,body=self.invoke(path="/healthz",peer="127.0.0.1")
        self.assertEqual(status,200)
        self.assertIs(body["upload_authorized"],False)

if __name__=="__main__":unittest.main()

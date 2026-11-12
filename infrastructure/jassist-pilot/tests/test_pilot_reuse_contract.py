"""Static security and live-inactive acceptance for reuse-based pilot package.

No Docker commands, AWS calls, network calls or production writes.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]


class JAssistReusePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=yaml.safe_load((ROOT/"resource-plan.yaml").read_text())
        cls.compose=yaml.safe_load((ROOT/"compose.pilot.yaml").read_text())
        spec=importlib.util.spec_from_file_location("jassist_pilot_disabled",
                 ROOT/"disabled_app.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.app=staticmethod(module.app)

    def test_existing_infrastructure_only_and_zero_aws_mutations(self):
        plan=self.resources
        self.assertEqual(plan["status"],"preproduction-not-deployed")
        self.assertEqual(plan["architecture"],
                         "reuse-existing-jason-host-and-aws-https-relay")
        self.assertEqual(plan["host"]["machine"],"Jason")
        self.assertEqual(plan["network"]["existing_public_https_host"],
                         "mcp-jason.teamaot.com")
        self.assertTrue(plan["network"]["zerotier_peers_require_fresh_verification"])
        for key,value in plan["aws"].items():
            if key.startswith("new_") or key=="mutations_performed":
                with self.subTest(key=key):self.assertEqual(value,0)
        self.assertFalse(plan["approval"]["existing_production_host_or_relay_changes_authorized"])

    def test_container_is_nonroot_isolated_and_not_network_exposed(self):
        compose=self.compose
        service=compose["services"]["jassist-pilot"]
        self.assertEqual(compose["name"],"jassist-pilot")
        self.assertEqual(service["restart"],"no")
        self.assertEqual(service["user"],"10001:10001")
        self.assertIs(service["read_only"],True)
        self.assertIn("no-new-privileges:true",service["security_opt"])
        self.assertEqual(service["cap_drop"],["ALL"])
        self.assertEqual(service["pids_limit"],64)
        self.assertEqual(service["mem_limit"],"768m")
        self.assertLessEqual(float(service["cpus"]),0.5)
        self.assertEqual(service["ports"],["127.0.0.1:3981:3981"])
        self.assertTrue(compose["networks"]["jassist-isolated"]["internal"])
        self.assertEqual(service["networks"],["jassist-isolated"])
        self.assertFalse(service.get("privileged",False))
        self.assertNotIn("network_mode",service)
        self.assertNotIn("volumes",service)
        self.assertNotIn("secrets",service)

    def test_reviewed_build_has_no_activation_or_secrets(self):
        dockerfile=(ROOT/"Dockerfile").read_text()
        requirements=(ROOT/"requirements.pilot.txt").read_text()
        self.assertIn("USER 10001:10001",dockerfile)
        self.assertIn("disabled_app:app",dockerfile)
        self.assertNotIn("docker.sock",dockerfile)
        self.assertNotIn("jason-runtime:",dockerfile)
        self.assertNotIn("/var/lib/jason/openclaw",dockerfile)
        self.assertNotIn("ADD https:",dockerfile)
        self.assertIn("cryptography==50.0.2",requirements)
        self.assertIn("PyJWT==2.13.0",requirements)
        self.assertIn("uvicorn==0.52.4",requirements)

    def test_same_existing_hostname_and_proposed_route_only(self):
        fragment=(ROOT/"caddy-route.PROPOSED.caddy").read_text()
        self.assertIn("@jassist_pilot path /v1/jassist/*",fragment)
        self.assertIn("10.87.246.157:3981",fragment)
        self.assertIn("DO NOT APPLY",fragment)
        self.assertNotIn("api/messages",fragment)
        self.assertNotIn("reverse_proxy 0.0.0.0",fragment)

    @staticmethod
    async def _invoke(app,scope):
        events=[]
        async def receive():
            return {"type":"http.request","body":b"","more_body":False}
        async def send(event):
            events.append(event)
        await app(scope,receive,send)
        return events

    def test_live_entrypoint_remains_inactive_even_with_browser_origin(self):
        scope={"type":"http","path":"/v1/jassist/readiness","method":"GET",
               "headers":[(b"origin",
                    b"chrome-extension://pihjpgplfhmpenlghbcdbgdkadleflfi")]}
        response=asyncio.run(self._invoke(self.app,scope))
        self.assertEqual(response[0]["status"],503)
        self.assertEqual(json.loads(response[1]["body"])["status"],"unavailable")
        self.assertTrue(any(k==b"access-control-allow-origin"
                            for k,v in response[0]["headers"]))
        scope["path"]="/v1/jassist/image"
        scope["method"]="POST"
        response=asyncio.run(self._invoke(self.app,scope))
        self.assertEqual(response[0]["status"],503)

    def test_disabled_health_endpoint_never_claims_ready(self):
        response=asyncio.run(self._invoke(self.app,
                 {"type":"http","method":"GET","path":"/healthz","headers":[]}))
        self.assertEqual(response[0]["status"],200)
        status=json.loads(response[1]["body"])
        self.assertEqual(status["state"],"inactive")
        self.assertIs(status["ingress_ready"],False)
        for path in ("/v1/jassist/session","/v1/jassist/session/validate",
                     "/v1/jassist/session/stop","/v1/jassist/image"):
            with self.subTest(path=path):
                response=asyncio.run(self._invoke(self.app,
                    {"type":"http","method":"POST","path":path,"headers":[]}))
                self.assertEqual(response[0]["status"],503)


if __name__=="__main__":
    unittest.main()

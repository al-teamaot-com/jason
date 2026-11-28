from __future__ import annotations
from dataclasses import replace
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.mcp_activation import JAssistReleaseAttestation,activate_jassist
from jassist.runtime_wiring import JAssistRunningComponents
from jassist.chatgpt_image_tool import ChatGPTImageEvidenceTool

class App:
    def __init__(self):self.calls=[]
    def mount(self,*args,**kwargs):self.calls.append((args,kwargs))

class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.app=App()
        self.tools={}
        self.components=JAssistRunningComponents(
            api=None,gateway=object(),
            mcp_image_tool=ChatGPTImageEvidenceTool.__new__(ChatGPTImageEvidenceTool),
            durable_gate=None)
        self.attest=JAssistReleaseAttestation(
            candidate_sha="a"*40,deployed_sha="a"*40,
            rollback_sha="c"*40,
            reviewed_scope_sha256="b"*64,owner_approval_receipt="OWNER-APPROVAL-TEST",
            protected_main_verified=True,runtime_health_verified=True,
            rollback_readback_verified=True,safe_review_enabled=True)
    def activate(self,**changes):
        args={"app":self.app,
              "register_mcp_tool":lambda f:self.tools.setdefault(f.__name__,f),
              "components":self.components,
              "authenticated_mcp_identity":lambda:("tech","aot","entra-oauth-bearer",None),
              "attest":self.attest,
              "enabled_by_governed_configuration":lambda:True,
              "image_read_enabled":lambda:True,
              "verify_governed_release_attestation":lambda proof:True}
        args.update(changes)
        return activate_jassist(**args)
    def test_unapproved_release_cannot_register_or_mount(self):
        fields=(
            {"deployed_sha":"c"*40},{"candidate_sha":"not-a-sha"},
            {"rollback_sha":"a"*40},{"rollback_sha":"bad"},
            {"reviewed_scope_sha256":""},{"owner_approval_receipt":""},
            {"protected_main_verified":False},{"runtime_health_verified":False},
            {"rollback_readback_verified":False},
            {"safe_review_enabled":False})
        for changed in fields:
            with self.subTest(changed=changed),self.assertRaises(PermissionError):
                self.activate(attest=replace(self.attest,**changed))
            self.assertEqual(self.tools,{})
            self.assertEqual(self.app.calls,[])
        with self.assertRaises(PermissionError):
            self.activate(enabled_by_governed_configuration=lambda:False)
        self.assertEqual(self.tools,{})
        self.assertEqual(self.app.calls,[])
    def test_exact_release_requires_independent_authoritative_verifier(self):
        with self.assertRaises(PermissionError):
            self.activate(verify_governed_release_attestation=lambda proof:False)
        with self.assertRaises(PermissionError):
            self.activate(verify_governed_release_attestation=None)
        with self.assertRaises(PermissionError):
            self.activate(verify_governed_release_attestation=lambda proof:1)
        self.assertEqual(self.tools,{})
        self.assertEqual(self.app.calls,[])

    def test_existing_mcp_registry_and_isolated_ingress_require_exact_proof(self):
        report=self.activate()
        self.assertEqual(report["registered"],True)
        self.assertIn("read_jassist_reviewed_image",self.tools)
        self.assertEqual(len(self.app.calls),1)
        self.assertEqual(self.app.calls[0][0][0],"/v1/jassist")
        self.assertEqual(self.app.calls[0][1]["name"],"jassist-reviewed-evidence")
    def test_no_deployment_capability_when_components_missing(self):
        with self.assertRaises(ValueError):self.activate(components=None)
        self.assertEqual(self.tools,{})

if __name__=="__main__":unittest.main()

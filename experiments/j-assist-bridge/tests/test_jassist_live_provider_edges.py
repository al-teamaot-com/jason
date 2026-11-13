"""J-Assist live-provider adapters: no new grants, network or host changes."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"implementation"))
from jassist.governed_aes_keys import GovernedJAssistKeyBroker
from jassist.pinned_entra_jwks import PinnedAotEntraJwks
from jassist.reviewed_frame_allowlist import AttestedPilotFrameReview
from jassist.entra_send_authority import AOT_ENTRA_TENANT_ID

JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"non-sensitive synthetic test frame" + bytes.fromhex("ffd9")

class JAssistLiveProviderEdgesTests(unittest.TestCase):
    def test_no_reused_keys_and_no_fallback(self):
        a=base64.b64encode(b"a"*32).decode()
        b=base64.b64encode(b"b"*32).decode()
        source={"jassist.session_encryption":{"key_b64":a},
                "jassist.evidence_encryption":{"key_b64":b}}
        provider=GovernedJAssistKeyBroker(resolve=source.__getitem__)
        pair=provider.load()
        self.assertEqual(pair.session,b"a"*32)
        self.assertEqual(pair.evidence,b"b"*32)
        source["jassist.evidence_encryption"]={"key_b64":a}
        with self.assertRaises(ValueError): provider.load()
        del source["jassist.session_encryption"]
        with self.assertRaises(PermissionError): provider.load()
        source["jassist.session_encryption"]={"key_b64":"not_base64"}
        with self.assertRaises(PermissionError): provider.load()
        source["jassist.session_encryption"]={"key_b64":a,"unrelated":"unapproved"}
        with self.assertRaises(PermissionError): provider.load()

    def test_pinned_aot_tenant_jwks_never_follows_untrusted_key_url(self):
        rsa_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        class SigningKey:
            key=rsa_key.public_key()
        class JwksClient:
            def __init__(self): self.calls=0
            def get_signing_key_from_jwt(self,token):
                self.calls+=1
                return SigningKey()
        provider=JwksClient()
        jwks=PinnedAotEntraJwks(client=provider)
        self.assertIn(AOT_ENTRA_TENANT_ID,jwks.url)
        claims={"aud":"test", "exp":9999999999}
        valid=jwt.encode(claims,rsa_key,algorithm="RS256",headers={"kid":"signed-test-key"})
        self.assertEqual(jwks(valid),rsa_key.public_key())
        self.assertEqual(provider.calls,1)
        for headers in ({"kid":"signed-test-key","jku":"https://untrusted.test/jwks"},
                        {"kid":"signed-test-key","crit":["none"]}):
            with self.assertRaises(ValueError):
                jwks(jwt.encode(claims,rsa_key,algorithm="RS256",headers=headers))
        self.assertEqual(provider.calls,1)
        with self.assertRaises(ValueError):
            jwks(jwt.encode(claims,"secret",algorithm="HS256",headers={"kid":"k"}))

    def test_positive_only_review_requires_independent_manifest_approval(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder=Path(temp.name)
        path=folder/"approved.json"
        manifest={"schema_version":1,"enabled":True,
                  "reviewer_id":"OWNER-TEST-REVIEW",
                  "policy_version":"PILOT-APPROVAL-REV1",
                  "approved_sha256":[hashlib.sha256(JPEG).hexdigest()]}
        path.write_text(json.dumps(manifest,sort_keys=True))
        path.chmod(0o600)
        allowed_hashes={hashlib.sha256(path.read_bytes()).hexdigest()}
        reviewer=AttestedPilotFrameReview(
            policy_path=path,
            verify_current_manifest=lambda digest:digest in allowed_hashes)
        decision=reviewer(JPEG)
        self.assertEqual(decision.image,JPEG)
        self.assertEqual(decision.reviewer_id,"OWNER-TEST-REVIEW")
        with self.assertRaises(PermissionError):
            reviewer(JPEG+b"modified")
        manifest["approved_sha256"]=["0"*64]
        path.write_text(json.dumps(manifest,sort_keys=True))
        with self.assertRaises(PermissionError):
            reviewer(JPEG)
        allowed_hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(PermissionError):
            reviewer(JPEG)
        path.chmod(0o644)
        with self.assertRaises(PermissionError):
            reviewer(JPEG)
        path.chmod(0o600)
        manifest["enabled"]=False
        path.write_text(json.dumps(manifest,sort_keys=True))
        allowed_hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(PermissionError):
            reviewer(JPEG)

if __name__=="__main__":
    unittest.main()

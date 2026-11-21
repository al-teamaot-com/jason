"""Source-only scoped OpenBao/Entra/image-review pilot requirements."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]/"implementation"))
from jassist.jassist_access_policy import JAssistEntraAccessPolicy
from jassist.reviewed_frame_allowlist import AttestedPilotFrameReview


class PilotProviderScopeTests(unittest.TestCase):
    def test_openbao_policy_exact_two_nonprod_read_paths_no_wildcards(self):
        source=(ROOT/"openbao-scope.PROPOSED.hcl").read_text()
        pairs=re.findall(r'path "([^"]+)"\s*\{\s*capabilities = \[(.*?)\]\s*\}',
                         source,flags=re.S)
        self.assertEqual(len(pairs),2)
        self.assertEqual({p for p,_ in pairs},{
            "secret/data/pilots/jassist/nonproduction/session-encryption",
            "secret/data/pilots/jassist/nonproduction/evidence-encryption"
        })
        for path,capabilities in pairs:
            self.assertEqual(capabilities.strip(),'"read"')
            self.assertNotIn("*",path)
            self.assertNotIn("production/",path.replace("nonproduction/",""))
            self.assertNotIn("connectors/",path)

    def test_openbao_mapping_only_expected_separated_keys(self):
        source=json.loads((ROOT/"openbao-mapping.PROPOSED.json").read_text())
        self.assertEqual(source["status"],"not_provisioned")
        self.assertEqual(source["approle_name"],"jason-jassist-pilot-read")
        self.assertFalse(source["bootstrap_role_secret_id_provisioned"])
        self.assertFalse(source["unique_aes256_keys_provisioned"])
        self.assertFalse(source["production_connector_creds_exposed"])
        self.assertEqual(set(source["keys"]),{
            "jassist.session_encryption","jassist.evidence_encryption"
        })
        paths=[]
        for item in source["keys"].values():
            self.assertEqual(item["exact_fields"],["key_b64"])
            paths.append(item["kv_v2_path"])
        self.assertEqual(len(set(paths)),2)

    def test_entra_consent_is_unverified_and_exact_one_pilot_client(self):
        data=json.loads((ROOT/"entra-consent.PROPOSED.json").read_text())
        self.assertEqual(data["status"],"unverified_do_not_grant_automatically")
        self.assertEqual(data["spa_pilot_client_id"],
                         "d1cc801b-13ba-4d44-bea6-e7f08186e4d5")
        self.assertEqual(data["delegated_scope_required"],"JAssist.Send")
        self.assertTrue(data["legacy_jason_read_scope_must_remain_unchanged"])
        self.assertFalse(data["spa_client_secret_required"])
        for field in ("independent_graph_admin_consent_readback_verified",
                      "independent_spa_scope_consent_verified",
                      "independent_current_group_membership_verified"):
            self.assertIs(data[field],False)
        browser_source=(ROOT.parents[1]/"experiments/chrome-datto-observer/entra_pkce.js").read_text()
        self.assertIn(data["spa_pilot_client_id"],browser_source)
        self.assertIn(data["group_eligibility_id"],
                      json.dumps(json.loads((ROOT/"access-policy.DISABLED.example.json").read_text())))

    def test_source_only_policies_reject_activation(self):
        source=json.loads((ROOT/"access-policy.DISABLED.example.json").read_text())
        policy=JAssistEntraAccessPolicy.from_mapping(source)
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.scope,"screen_assistance")
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            copy=folder/"review.json"
            shutil.copyfile(ROOT/"review-policy.DISABLED.example.json",copy)
            copy.chmod(0o600)
            digest=hashlib.sha256(copy.read_bytes()).hexdigest()
            reviewer=AttestedPilotFrameReview(
                policy_path=copy,
                verify_current_manifest=lambda candidate:candidate==digest
            )
            self.assertIs(reviewer.ready(),False)
            with self.assertRaises(PermissionError):
                reviewer(b"\xff\xd8\xff\xd9")


if __name__=="__main__":
    unittest.main()

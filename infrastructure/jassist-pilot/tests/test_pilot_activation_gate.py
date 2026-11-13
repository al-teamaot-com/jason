"""Exact-scope J-Assist activation candidate must fail closed."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pilot_activation_admission as gate


class PilotActivationGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=gate.load_candidate(ROOT/"activation-candidate.json")
        gate.validate_manifest(cls.original)

    def test_actual_manifest_is_no_go_without_ledger_or_provider_evidence(self):
        result=gate.check_admission(copy.deepcopy(self.original))
        self.assertFalse(result.ready)
        self.assertIn("governance_evidence_verifier_unavailable",result.failures)
        self.assertIn("production_rollback_sha_not_independently_verified",result.failures)
        self.assertIn("datto_by_id_native_uuid_account_binding:evidence_reference_missing",result.failures)
        self.assertIn("entra_app_graph_user_group_membership:evidence_reference_missing",result.failures)
        self.assertIn("production_health_and_release_controls:evidence_reference_missing",result.failures)
        self.assertEqual(result.checked_gates,())

    @staticmethod
    def complete_synthetic_candidate():
        manifest=copy.deepcopy(PilotActivationGateTests.original)
        manifest["candidate_protected_main_sha"]="a"*40
        manifest["scope_sha256"]="b"*64
        manifest["verified_production_rollback_sha"]="c"*40
        for key in manifest["evidence"]:
            manifest["evidence"][key]="synthetic-ledger-ref-20261112-"+key
        return manifest

    def test_separately_authenticated_governance_ledger_is_required(self):
        manifest=self.complete_synthetic_candidate()
        self.assertFalse(gate.check_admission(manifest).ready)
        calls=[]
        def trusted_ledger(name,ref,candidate):
            calls.append(name)
            return ref.endswith(name) and candidate is manifest
        result=gate.check_admission(manifest,independently_verify=trusted_ledger)
        self.assertTrue(result.ready)
        self.assertEqual(set(calls),set(manifest["evidence"]))
        self.assertEqual(result.failures,())
        self.assertEqual(len(result.checked_gates),13)

    def test_independent_verifier_denial_exception_and_truthy_not_true_fail(self):
        candidate=self.complete_synthetic_candidate()
        target="owner_exact_route_action_approval"
        def conditional(name,ref,scope):
            if name==target:
                return 1
            return True
        verdict=gate.check_admission(candidate,independently_verify=conditional)
        self.assertFalse(verdict.ready)
        self.assertIn(target+":independent_verification_denied",verdict.failures)
        def unavailable(name,ref,scope):
            if name==target:
                raise TimeoutError("approval ledger cannot be reached")
            return True
        verdict=gate.check_admission(candidate,independently_verify=unavailable)
        self.assertFalse(verdict.ready)
        self.assertIn(target+":independent_verification_unavailable",verdict.failures)

    def test_expired_or_revoked_owner_release_evidence_deny(self):
        candidate=self.complete_synthetic_candidate()
        def current_owner(name,ref,scope):
            return name!="owner_exact_route_action_approval"
        verdict=gate.check_admission(candidate,independently_verify=current_owner)
        self.assertFalse(verdict.ready)

    def test_actual_production_drift_breaker_open_deny_even_if_others_pass(self):
        candidate=self.complete_synthetic_candidate()
        def trusted_ledger(name,ref,scope):
            return name!="production_health_and_release_controls"
        verdict=gate.check_admission(candidate,independently_verify=trusted_ledger)
        self.assertFalse(verdict.ready)
        self.assertIn("production_health_and_release_controls:independent_verification_denied",verdict.failures)

    def test_reject_changes_to_pinned_device_tenant_route_or_authority(self):
        choices={
            "entra_group_id":"11111111-1111-4111-8111-111111111111",
            "datto_browser_device_id":"99999999",
            "datto_site_uid":"99999999-9999-4999-8999-999999999999",
            "retention_seconds":7200,
            "production_deployment_authorized":True,
            "requires_exact_action_owner_authorization":False,
            "pilot_upstream":"0.0.0.0:3981",
            "new_aws_resources":1,
            "status":"enabled",
            "post_activation_acceptance":[],
        }
        for field,bad in choices.items():
            with self.subTest(field=field):
                item=copy.deepcopy(self.original)
                item[field]=bad
                with self.assertRaises(ValueError):
                    gate.check_admission(item,independently_verify=lambda *a:True)

    def test_reject_unknown_evidence_and_duplicate_json_fields(self):
        obj=copy.deepcopy(self.original)
        obj["evidence"]["model_unrestricted_upload"]="approve"
        with self.assertRaises(ValueError):
            gate.validate_manifest(obj)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"dup.json"
            p.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):
                gate.load_candidate(p)

    def test_deny_same_source_as_rollback(self):
        item=self.complete_synthetic_candidate()
        item["verified_production_rollback_sha"]=item["candidate_protected_main_sha"]
        result=gate.check_admission(item,independently_verify=lambda *a:True)
        self.assertFalse(result.ready)
        self.assertIn("production_rollback_sha_not_independently_verified",result.failures)

    def test_cli_can_only_report_no_go_and_never_writes_or_deploys(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_env=Path(temp)
            cp=subprocess.run([sys.executable,str(ROOT/"pilot_activation_admission.py"),
                               "--manifest",str(ROOT/"activation-candidate.json")],
                              capture_output=True,text=True,check=False,cwd=fake_env)
            self.assertEqual(cp.returncode,2)
            report=json.loads(cp.stdout)
            self.assertEqual(report["pilot_admission"],"NO_GO")
            self.assertFalse(report["writes_performed"])
            self.assertEqual(list(fake_env.iterdir()),[])


if __name__=="__main__":
    unittest.main()

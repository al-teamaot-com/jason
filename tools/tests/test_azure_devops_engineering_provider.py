"""No-network release evidence regression tests for Azure DevOps provider adapter."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools" / "azure_devops_engineering_provider.py"
spec = importlib.util.spec_from_file_location("azure_devops_engineering_provider", MODULE)
provider = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = provider
spec.loader.exec_module(provider)
SHA = "a" * 40


class FakeAzure:
    def __init__(self, *, main=SHA, branch="refs/heads/main", build_sha=SHA,
                 build_result="succeeded", job_result="succeeded", include=True):
        self.calls = []
        self.main, self.branch = main, branch
        self.build_sha, self.build_result = build_sha, build_result
        self.job_result, self.include = job_result, include

    def __call__(self, method, url, data):
        self.calls.append((method, url))
        if "/refs?" in url:
            return {"value": [{"name": "refs/heads/main", "objectId": self.main}]}
        if "/pullrequests?" in url:
            return {"value": [{"pullRequestId": 4, "isDraft": True}]}
        if "/wit/wiql?" in url:
            return {"workItems": [{"id": 1}, {"id": 3}]}
        if "/timeline?" in url:
            return {"records": [{"type": "Job", "name": "GateJob",
                                 "state": "completed", "result": self.job_result}]}
        if "/build/builds?" in url:
            rows = [{
                "id": 10, "sourceVersion": self.build_sha,
                "sourceBranch": self.branch,
                "definition": {"id": 2},
                "status": "completed", "result": self.build_result
            }]
            return {"value": rows if self.include else []}
        raise AssertionError(url)


class EngineeringAdapterTests(unittest.TestCase):
    def check(self, fake, sha=SHA, mapping=None):
        obj = provider.AzureEngineeringReader(fake)
        return obj.build_evidence(
            sha, mapping or {"runtime-service": provider.BuildCheck(2, "GateJob")},
            ["runtime-service"])

    def test_main_sha_is_canonical(self):
        self.assertEqual(provider.AzureEngineeringReader(FakeAzure()).main_sha(), SHA)

    def test_pr_listing_is_read_only(self):
        fake = FakeAzure()
        result = provider.AzureEngineeringReader(fake).active_prs()
        self.assertEqual(result[0]["pullRequestId"], 4)
        self.assertTrue(all(method == "GET" for method, _ in fake.calls))

    def test_wiql_is_bounded_read_only(self):
        fake = FakeAzure()
        self.assertEqual(provider.AzureEngineeringReader(fake).work_items(), [1, 3])
        self.assertEqual([method for method, _ in fake.calls], ["POST"])
        self.assertIn("wit/wiql", fake.calls[0][1])

    def test_matching_main_build_and_job_succeeds(self):
        result = self.check(FakeAzure())
        self.assertTrue(result["passed"])
        self.assertEqual(result["provider"], "azure-devops")
        self.assertEqual(result["evidence"]["runtime-service"]["source_sha"], SHA)

    def test_fails_closed_for_non_main_candidate(self):
        with self.assertRaisesRegex(provider.AzureEvidenceError, "does not equal Azure main"):
            self.check(FakeAzure(main="b" * 40))

    def test_wrong_sha_build_rejected(self):
        self.assertFalse(self.check(FakeAzure(build_sha="b" * 40))["passed"])

    def test_feature_branch_build_rejected(self):
        self.assertFalse(self.check(FakeAzure(branch="refs/heads/feature/work"))["passed"])

    def test_failed_build_rejected(self):
        self.assertFalse(self.check(FakeAzure(build_result="failed"))["passed"])

    def test_failed_job_rejected(self):
        self.assertFalse(self.check(FakeAzure(job_result="failed"))["passed"])

    def test_missing_build_rejected(self):
        self.assertFalse(self.check(FakeAzure(include=False))["passed"])

    def test_missing_required_mapping_rejected(self):
        reader = provider.AzureEngineeringReader(FakeAzure())
        with self.assertRaisesRegex(provider.AzureEvidenceError, "mapping incomplete"):
            reader.build_evidence(SHA, {}, ["runtime-service"])

    def test_empty_required_checks_rejected(self):
        reader = provider.AzureEngineeringReader(FakeAzure())
        with self.assertRaisesRegex(provider.AzureEvidenceError, "Missing or duplicate"):
            reader.build_evidence(SHA, {}, [])

    def test_unknown_required_check_rejected(self):
        reader = provider.AzureEngineeringReader(FakeAzure())
        with self.assertRaisesRegex(provider.AzureEvidenceError, "Unexpected"):
            reader.build_evidence(SHA, {"made-up": provider.BuildCheck(2, "GateJob")},
                                   ["made-up"])

    def test_invalid_sha_rejected_before_network(self):
        fake = FakeAzure()
        with self.assertRaisesRegex(provider.AzureEvidenceError, "Invalid release SHA"):
            self.check(fake, "not-a-sha")
        self.assertEqual(fake.calls, [])

    def test_no_raw_external_url(self):
        fake = FakeAzure()
        with self.assertRaises(provider.AzureEvidenceError):
            provider.AzureEngineeringReader(fake)._get("https://evil.example/api")
        self.assertEqual(fake.calls, [])

    def test_transport_blocks_mutations_before_credentials(self):
        def forbidden():
            raise AssertionError("Should never resolve tokens on disallowed action")
        transport = provider.read_only_transport(forbidden)
        with self.assertRaises(provider.AzureEvidenceError):
            transport("POST", provider.BASE+"/git/repositories/"+provider.REPOSITORY_ID+"/pullrequests?api-version=7.1", {})
        with self.assertRaises(provider.AzureEvidenceError):
            transport("PATCH", provider.BASE+"/wit/workitems/1", {})
        with self.assertRaises(provider.AzureEvidenceError):
            transport("GET", "https://example.com/", None)

    def test_config_requires_nonzero_pipeline_id_and_job_name(self):
        for item in (provider.BuildCheck(0, "GateJob"), provider.BuildCheck(2, "")):
            with self.assertRaises(provider.AzureEvidenceError):
                item.validate()


if __name__ == "__main__":
    unittest.main()

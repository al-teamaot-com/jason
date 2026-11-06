"""Synthetic Azure PR governance parity tests; never contact GitHub or Azure."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
for name in ("azure_devops_engineering_provider","azure_devops_identity",
             "documentation_impact_gate","change_integration_gate","azure_devops_pr_gates"):
    if name in sys.modules:
        continue
    spec=importlib.util.spec_from_file_location(name,ROOT/"tools"/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
gates=sys.modules["azure_devops_pr_gates"]

VALID="## Documentation impact\n- [x] Documentation updated\nIntegration coordination: none"
ACK="## Documentation impact\n- [x] Documentation updated\nIntegration coordination: #5"
SHA="a"*40

class FakeReader:
    def __init__(self, body=VALID, draft=False, changed=None, peer=None, base=SHA):
        self.body=body; self.draft=draft
        self.changed=changed if changed is not None else {"tools/new.py"}
        self.peer=peer if peer is not None else set()
        self.base=base
    def pull_request(self,pr_id):
        return {"pullRequestId":pr_id,"status":"active",
                "targetRefName":"refs/heads/main","description":self.body,
                "isDraft":self.draft}
    def main_sha(self):return SHA
    def pr_base_sha(self,pr_id):return self.base
    def pull_request_files(self,pr_id):
        return self.changed if pr_id==4 else self.peer
    def active_prs(self):
        return [{"pullRequestId":4,"targetRefName":"refs/heads/main"},
                {"pullRequestId":5,"targetRefName":"refs/heads/main"}]

class AzurePrGatesTests(unittest.TestCase):
    def test_valid_pr_passes_without_overlap(self):
        self.assertEqual(gates.validate(FakeReader(),4)["status"],"pass")
    def test_draft_not_approved(self):
        self.assertEqual(gates.validate(FakeReader(draft=True),4)["status"],"blocked")
    def test_missing_doc_declaration_rejected(self):
        self.assertTrue(any("Documentation impact" in x
            for x in gates.validate(FakeReader(body="No declaration"),4)["errors"]))
    def test_stale_target_sha_fails_closed(self):
        self.assertTrue(any("stale" in x
            for x in gates.validate(FakeReader(base="b"*40),4)["errors"]))
    def test_overlap_without_ack_is_rejected(self):
        report=gates.validate(FakeReader(peer={"tools/new.py"}),4)
        self.assertTrue(any("overlap" in error for error in report["errors"]))
    def test_acknowledged_overlap_passes(self):
        report=gates.validate(FakeReader(body=ACK,peer={"tools/new.py"}),4)
        self.assertEqual(report["status"],"pass")
    def test_non_sensitive_overlap_does_not_block(self):
        report=gates.validate(FakeReader(changed={"README.md"},peer={"README.md"}),4)
        self.assertEqual(report["status"],"pass")

if __name__=="__main__":unittest.main()

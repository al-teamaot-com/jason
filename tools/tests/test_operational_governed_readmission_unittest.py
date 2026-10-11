import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import owner_approved_development_worker as worker
import todo_release_bridge as bridge

class OperationalReadmission(unittest.TestCase):
    def scenario(self, releases=None, operational=None, fresh=None, ledger_retry=True, issue_body=None):
        releases = releases if releases is not None else []
        operational = operational if operational is not None else []
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        spool = Path(root.name)
        candidate = {'issue_number':953,'phase':'development_blocked','blocker_category':'dependency',
                     'governing_dependencies':releases,'governing_operational_dependencies':operational,
                     'retry_eligible':ledger_retry}
        (spool/'todo-release-state.json').write_text(json.dumps({'items':{'TODO-OPS-003': candidate}}))
        if issue_body is None:
            issue_body=''.join(['- Governing release dependencies: '+','.join(releases)+'\n' if releases else '',
                                '- Governing operational dependencies: '+','.join(operational)+'\n' if operational else ''])
        item={'id':'DEV-953','issue_number':953,'body':issue_body}
        state={'items':{'DEV-953':{'phase':'blocked','blocker_class':'blocked_by_dependency'}}}
        return spool,item,state,fresh or {}
    def execute(self,spool,item,state,fresh):
        with patch.object(worker,'active_support_count',return_value=0),patch.object(worker.todo_bridge,'dependency_state_for_item',return_value=fresh):
            return worker.readmit_explicit_verified_dependencies(state,[item],spool,max_active=2)
    def test_operational_only_verified_once(self):
        s,i,st,f=self.scenario(operational=['acceptance-network-posture'],fresh={'retry_eligible':True,'operational_recheck':'verified','verified_operational_evidence':{'acceptance-network-posture':'governed:real-ref'}})
        self.assertEqual(self.execute(s,i,st,f),1)
        st['items']['DEV-953']['phase']='blocked'
        self.assertEqual(self.execute(s,i,st,f),0)
    def test_release_only_legacy(self):
        s,i,st,f=self.scenario(releases=['release-1234567890abcdef'],fresh={'retry_eligible':True,'dependency_recheck':'verified_for_governed_readmission_check'})
        self.assertEqual(self.execute(s,i,st,f),1)
    def test_combined_invalid_receipt_closed(self):
        s,i,st,f=self.scenario(releases=['release-1234567890abcdef'],operational=['acceptance-network-posture'],fresh={'retry_eligible':False,'dependency_recheck':'verified_for_governed_readmission_check','operational_recheck':'awaiting_authoritative_acceptance'})
        self.assertEqual(self.execute(s,i,st,f),0)
    def test_spoofed_ledger_cannot_override_authority(self):
        s,i,st,f=self.scenario(operational=['acceptance-network-posture'],fresh={'retry_eligible':True,'operational_recheck':'verified','verified_operational_evidence':{}})
        self.assertEqual(self.execute(s,i,st,f),0)
    def test_issue_declared_scope_must_match(self):
        s,i,st,f=self.scenario(operational=['acceptance-network-posture'],issue_body='- Governing operational dependencies: acceptance-other-scope',fresh={'retry_eligible':True,'operational_recheck':'verified','verified_operational_evidence':{'acceptance-network-posture':'governed:ref'}})
        self.assertEqual(self.execute(s,i,st,f),0)
    def test_no_dependencies_blocked(self):
        s,i,st,f=self.scenario(fresh={'retry_eligible':True})
        self.assertEqual(self.execute(s,i,st,f),0)
from tools.tests.test_operational_acceptance_reader import fixture

class SignedReceiptIntegration(unittest.TestCase):
    def test_signed_receipt_gates_exactly_once_recovery(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            spool=root/'spool'
            spool.mkdir()
            release_root=root/'release'
            protected=release_root/'protected-operational-acceptance'
            (protected/'receipts').mkdir(parents=True)
            receipt,trust=fixture()
            (protected/'trust.json').write_text(json.dumps(trust))
            identity='acceptance-network-posture'
            candidate={'issue_number':953,'phase':'development_blocked',
                'blocker_category':'dependency','governing_dependencies':[],
                'governing_operational_dependencies':[identity]}
            item={'id':'DEV-953','issue_number':953,'body':'- Governing operational dependencies: '+identity}
            state={'items':{'DEV-953':{'phase':'blocked','blocker_class':'blocked_by_dependency'}}}
            self.assertFalse(bridge.dependency_state_for_item(candidate,release_root)['retry_eligible'])
            (protected/'receipts'/(identity+'.json')).write_text(json.dumps(receipt))
            valid=bridge.dependency_state_for_item(candidate,release_root)
            self.assertTrue(valid['retry_eligible'])
            candidate.update(valid)
            (spool/'todo-release-state.json').write_text(json.dumps({'items':{'TODO-OPS-003':candidate}}))
            with patch.object(worker,'active_support_count',return_value=0),patch.object(worker.todo_bridge,'DEFAULT_RELEASE_STATE',release_root):
                self.assertEqual(worker.readmit_explicit_verified_dependencies(state,[item],spool,max_active=2),1)
                state['items']['DEV-953']['phase']='blocked'
                self.assertEqual(worker.readmit_explicit_verified_dependencies(state,[item],spool,max_active=2),0)
                trust['revoked_receipts']=[receipt['payload']['receipt_id']]
                (protected/'trust.json').write_text(json.dumps(trust))
                state['items']['DEV-953'].pop('verified_dependency_readmission_key',None)
                self.assertEqual(worker.readmit_explicit_verified_dependencies(state,[item],spool,max_active=2),0)

if __name__=='__main__':
    unittest.main(verbosity=2)

"""Four PMv4 safeguards tested using the EXISTING Jason components.

Source-only; no provider calls, production state changes, external runner,
daemon, new database, restart or release. Runs in existing System Registry CI job.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'implementation'))
sys.path.insert(0,str(ROOT/'tools'))

from kernel.system_registry.manifest import registry_from_manifest
import pmv3_work_engine as engine
import engineering_supervisor as supervisor
from pmv4_workboard_reconciliation import reconciled_card


class ReliabilityAcceptance(unittest.TestCase):
    def test_durable_owner_mapping_does_not_silently_admit_unknown_objective(self):
        card={'id':'pmv4-accepted-0001','status':'ready','agentId':'j-dev'}
        state=engine.empty_state()
        unadmitted=reconciled_card(card,state)
        self.assertEqual(unadmitted['disposition'],'NOT_ADMITTED')
        self.assertFalse(unadmitted['eligible_for_automated_retry'])
        self.assertFalse(unadmitted['operational_completion_verified'])
        work_id='PMV4-WB-'+hashlib.sha256(card['id'].encode()).hexdigest()[:16].upper()
        entry=engine.make_item(work_id,'offline_jman_delegated_review',approved=True,idempotent=True)
        self.assertTrue(engine.admit(state,entry))
        self.assertFalse(engine.admit(state,entry), 'duplicate accepted objective must not create a second job')
        with tempfile.TemporaryDirectory(prefix='pmv4-work-owner-') as td:
            record=Path(td)/'state.json'
            engine.atomic_write(record,state)
            reread=engine.load_state(record)
            self.assertEqual(set(reread['items']),{work_id})
            self.assertEqual(reconciled_card(card,reread)['disposition'],'IN_PROGRESS')
        untrusted={**card,'agentId':'unknown-superuser'}
        self.assertEqual(reconciled_card(untrusted,state)['reason'],'agent_not_allowlisted')

    def test_supervisor_detects_stall_and_separates_governed_authority_holds(self):
        with tempfile.TemporaryDirectory(prefix='pmv4-stall-') as td:
            spool=Path(td)
            (spool/'state.json').write_text(json.dumps({'items':{
                'SUPPORT-OPS-010':{'phase':'blocked','reason':'Missing exact source excerpt'},
            }}))
            (spool/'development-state.json').write_text(json.dumps({'items':{
                'DEV-101':{'phase':'blocked','reason':'HTTP transport failed'},
            }}))
            (spool/'todo-intake-state.json').write_text(json.dumps({
                'active_development_items':0,'active_support_repairs':0,
                'engineering_capacity':2,
                'downstream_commitments':{'outstanding_count':2,'items':[
                    {'id':'TODO-OPS-010','phase':'development_blocked','reason':'Owner approval required'},
                ]},
            }))
            first=supervisor.build_snapshot(spool)
            second=supervisor.build_snapshot(spool,first)
            self.assertEqual(first['status'],'degraded')
            self.assertEqual(first['reason'],'internal_recovery_needed')
            self.assertEqual(second['unchanged_cycles'],1)
            self.assertEqual(first['category_counts']['human_authority'],1)
            self.assertEqual(first['action_owner'],'existing_governed_worker_or_verified_human')
            self.assertIn('SUPPORT-OPS-010',[i['id'] for i in first['items']])
            self.assertIn('DEV-101',[i['id'] for i in first['items']])
            self.assertEqual(
                supervisor.classify('development_blocked','Owner approval required',lane='development')[0],
                'human_authority',
            )

    def test_existing_system_registry_exposes_reverse_impact_dependencies(self):
        manifest=ROOT/'implementation/kernel/system_registry/production-registry.json'
        registry=registry_from_manifest(manifest)  # uses canonical schema and validation, not a new registry
        entities={e.registry_id:e for e in registry.list_all()}
        self.assertGreater(len(entities),200)
        self.assertIn('component.openclaw-gateway',entities)
        self.assertIn('component.jason-runtime',entities['component.openclaw-gateway'].dependencies)
        self.assertIn('component.openclaw-jason-bridge',entities)
        self.assertIn('component.openclaw-gateway',entities['component.openclaw-jason-bridge'].dependencies)
        impacted={name for name,e in entities.items()
                  if 'component.openclaw-gateway' in e.dependencies}
        self.assertIn('component.openclaw-jason-bridge',impacted)
        # Registry's own validation must reject unknown dependencies, not invent topology.
        malformed=json.loads(manifest.read_text())
        next(e for e in malformed['entities'] if e['registry_id']=='component.openclaw-gateway')['dependencies'].append(
            'component.nonexistent-pmv4-replacement')
        with tempfile.TemporaryDirectory(prefix='pmv4-registry-') as td:
            path=Path(td)/'malformed.json'
            path.write_text(json.dumps(malformed))
            with self.assertRaisesRegex(ValueError,'missing or cyclic dependencies'):
                registry_from_manifest(path)

    def test_operational_completion_requires_independent_acceptance(self):
        card={'id':'pmv4-card-completion-0001','status':'done','agentId':'j-dev',
              'metadata':{'proof':[{'id':'self-proof','status':'passed','note':'self-report is not acceptance'}]}}
        state=engine.empty_state()
        work_id='PMV4-WB-'+hashlib.sha256(card['id'].encode()).hexdigest()[:16].upper()
        engine.admit(state,engine.make_item(work_id,'offline_jdev_review'))
        state['items'][work_id]['phase']='complete'
        receipt_key=engine.action_key(work_id,'offline_jdev_review',1)
        state['receipts'][receipt_key]={'item_id':work_id,'receipt':'reported-durable-receipt'}
        before=copy.deepcopy(state)
        result=reconciled_card(card,state)
        self.assertEqual(result['disposition'],'REVIEW')
        self.assertEqual(result['reason'],'dual_completion_records_present_independent_acceptance_required')
        self.assertFalse(result['operational_completion_verified'])
        self.assertEqual(state,before)
        # A missing durable receipt is an actual blocker, even with a positive card.
        state['receipts'].clear()
        result=reconciled_card(card,state)
        self.assertEqual(result['disposition'],'BLOCKED')
        self.assertFalse(result['operational_completion_verified'])

    def test_new_requirements_reuse_existing_controls_without_production_authority(self):
        text=(ROOT/'config/openclaw-specialists/shared/PMV4-DEVELOPMENT-CONTRACT.md').read_text()
        for phrase in (
            'Guaranteed task ownership', 'Automatic stall recovery',
            'Dependency and impact checks', 'Operational readiness verification',
            'tools/engineering_supervisor.py','tools/pmv3_work_engine.py',
            'implementation/kernel/system_registry/', 'Release Manager',
            'no authorization for production changes',
        ):
            # Source-only policy is precise; known module paths are not invented.
            self.assertIn(phrase.lower(),text.lower())


if __name__=='__main__':
    unittest.main()

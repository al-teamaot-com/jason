from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UNITS=ROOT/'infrastructure/isolated-services'


def test_source_only_unit_inventory_and_admission_gate():
    manifest=json.loads((UNITS/'installation-manifest.json').read_text())
    assert manifest['production_deployment_authorized'] is False
    assert manifest['default_enable_all_new_units'] is False
    assert 'tools/pmv3_worker_release_gate.py' in manifest['required_companion_sources']
    assert len(manifest['unit_sources'])==10
    for source in manifest['unit_sources']:
        assert (ROOT/source).is_file()
    for lane in ('support','todo-intake','development','supervisor'):
        body=(UNITS/f'jason-independent-{lane}.service').read_text()
        assert 'ConditionPathExists=/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json' in body
        assert 'ConditionPathExists=/home/al/.local/lib/jason/pmv3_worker_release_gate.py' in body
        assert 'ExecCondition=/usr/bin/python3 /home/al/.local/lib/jason/pmv3_worker_release_gate.py' in body
        assert 'User=al' in body
        assert 'Group=al' in body
        assert 'NoNewPrivileges=true' in body
        assert 'ProtectSystem=strict' in body
        assert 'jason-support-repair-worker.service' not in body
    assert 'ExecStart=/usr/bin/python3 /usr/local/lib/jason/isolated_service_shadow.py' in (UNITS/'jason-isolated-shadow@.service').read_text()


def test_ticket_processing_continuity_is_a_release_no_go_requirement():
    manifest=json.loads((UNITS/'installation-manifest.json').read_text())
    rules=manifest['ticket_continuity_release_gate']
    assert rules['required_before_any_new_worker_activation'] is True
    assert rules['require_baseline_and_post_change_readback'] is True
    assert rules['require_controlled_test_ticket_mutation_evidence'] is True
    assert rules['require_zero_duplicate_ticket_actions_or_claims'] is True
    assert rules['require_explicit_no_go_on_unknown_or_failed_receipts'] is True
    assert rules['require_two_distinct_post_migration_observations'] is True
    assert manifest['production_deployment_authorized'] is False
    assert manifest['default_enable_all_new_units'] is False
    for unit_name in manifest['unit_sources']:
        source=(ROOT/unit_name).read_text()
        assert 'ExecStop=' not in source
        assert 'Conflicts=jason-runtime' not in source
        assert 'systemctl stop jason-runtime' not in source
        assert 'jason-autotask-ticket' not in source


def test_ticket_continuity_preflight_cannot_mint_native_approval():
    manifest=json.loads((UNITS/'installation-manifest.json').read_text())
    rules=manifest['ticket_continuity_release_gate']
    assert rules['evidence_preflight_source']=='tools/ticket_continuity_evidence_review.py'
    assert rules['preflight_positive_result']=='evidence_review_required (not approval)'
    assert rules['native_provider_reverification_mandatory'] is True
    assert rules['automation_can_mint_approval'] is False
    assert (ROOT/rules['evidence_preflight_source']).is_file()

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

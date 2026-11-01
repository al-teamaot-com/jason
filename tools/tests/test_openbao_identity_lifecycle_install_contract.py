from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def test_identity_lifecycle_units_are_managed_production_state():
    policy = json.loads((ROOT / 'config/production-desired-state.json').read_text())
    assert 'jason-openbao-identity-lifecycle.timer' in policy['required_system_units']
    assert 'jason-openbao-identity-lifecycle.service' in policy['allowed_system_units']


def test_identity_lifecycle_systemd_is_root_bounded_and_exact_path_writable():
    unit = (ROOT / 'infrastructure/openclaw-operations/systemd/jason-openbao-identity-lifecycle.service').read_text()
    assert 'User=root' in unit
    assert 'NoNewPrivileges=true' in unit
    assert 'ProtectSystem=strict' in unit
    assert 'ExecStart=/usr/bin/python3 /usr/local/lib/jason/openbao_identity_lifecycle_worker.py' in unit
    assert '/var/lib/jason/openclaw/identity-lifecycle' in unit
    assert '/opt/jason/bootstrap/secrets/openbao/autotask-read-approle' in unit
    assert '/var/lib/jason/runtime-secrets/openbao/dnsfilter-read-approle' in unit


def test_host_reconcile_installs_and_verifies_identity_lifecycle_worker():
    text = (ROOT / 'tools/reconcile_production_host_services.sh').read_text()
    assert 'step_start openbao_identity_lifecycle_install' in text
    assert 'install_openbao_identity_lifecycle.py' in text
    assert 'JASON_OPENBAO_IDENTITY_LIFECYCLE_RECONCILIATION=PASS' in text
    assert text.index('step_start root_release_transition_install') < text.index('step_start openbao_identity_lifecycle_install')
    assert text.index('step_start openbao_identity_lifecycle_install') < text.index('step_start production_drift_guard')


def test_host_reconcile_runs_provider_identity_recovery_before_final_drift_checks():
    text = (ROOT / 'tools/reconcile_production_host_services.sh').read_text()
    assert 'provider_identity_and_authority_recovery' in text
    assert 'recover-release --source-revision "$SOURCE_REVISION"' in text
    assert 'docker restart jason-runtime jason-mcp-pilot' in text
    assert 'jason-provider-health-canary.service' in text
    assert 'jason-dnsfilter-boundary-reconcile.service' in text
    recovery = text.index('step_start provider_identity_release_recovery')
    drift = text.index('step_start production_drift_guard')
    assert recovery < drift

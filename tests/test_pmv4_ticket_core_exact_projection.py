"""Pure Stage C isolation projection; no provider or host files touched."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_ticket_core_exact_projection as gate


def test_exact_reviewed_state_and_individual_credentials_only():
    mounts=list(gate.expected_docker_mounts())
    result=gate.validate_exact_mounts(mounts)
    assert result=={
        "mount_shape":"reviewed_exact_v1",
        "state_mount_count":5,
        "credential_mount_count":29,
        "provider_requests_executed":False,
        "root_owner_release_verified":False,
    }
    assert all(m["Source"] != "/var/lib/jason/openclaw" for m in mounts)
    assert all(m["Destination"] != "/var/lib/jason/openclaw" for m in mounts)
    assert set(gate.PROVIDER_STATE) <= {m["Source"] for m in mounts}
    assert all(m["RW"] is False for m in mounts[len(gate.STATE_MOUNTS):])
    assert set(m["Destination"] for m in mounts[len(gate.STATE_MOUNTS):]) == set(
        t for _,t in gate.CREDENTIAL_MOUNTS)


@pytest.mark.parametrize("change",[
    lambda m:m[0].update(RW=False),
    lambda m:m[0].update(Source="/var/lib/jason/openclaw"),
    lambda m:m[1].update(Source="/tmp/authority"),
    lambda m:m[2].update(Destination="/var/lib/jason/other"),
    lambda m:m[len(gate.STATE_MOUNTS)].update(RW=True),
    lambda m:m[len(gate.STATE_MOUNTS)].update(Source="/etc/shadow"),
    lambda m:m[len(gate.STATE_MOUNTS)].update(Destination="/run/jason-secrets/openbao/other"),
    lambda m:m[len(gate.STATE_MOUNTS)].update(Type="volume"),
    lambda m:m[len(gate.STATE_MOUNTS)].update(Source="/run/../jason-runtime-credentials/openbao/autotask/role_id"),
    lambda m:m.append({"Type":"bind","Source":"/var/run/docker.sock",
                       "Destination":"/var/run/docker.sock","RW":False}),
    lambda m:m.append(dict(m[len(gate.STATE_MOUNTS)])),
    lambda m:m.pop(len(gate.STATE_MOUNTS)),
])
def test_foreign_mount_or_widened_credential_denied(change):
    mounts=[dict(x) for x in gate.expected_docker_mounts()]
    change(mounts)
    with pytest.raises(gate.ProjectionDenied,match="CORE_EXACT_"):
        gate.validate_exact_mounts(mounts)


def test_malformed_mount_entries_denied():
    for bad in (None,{},[],[None],["bad"],["/var/lib/jason/openclaw"]):
        with pytest.raises(gate.ProjectionDenied,match="CORE_EXACT_"):
            gate.validate_exact_mounts(bad)


def settings(**updates):
    fields={k:Path(v) for k,v in gate.STATE_PATHS.items()}
    fields.update(ticket_worker_hosting="external",autonomy_worker_enabled=True)
    fields.update(updates)
    return SimpleNamespace(**fields)


def test_exact_state_paths_or_explicit_effective_default_required():
    result=gate.validate_exact_settings(settings())
    assert result=={
        "status":"source_paths_reviewed",
        "external_worker_ready":False,
        "owner_authorization_issued":False,
        "production_mutations":False,
    }
    fallback=settings(microsoft_boundary_db=None,reflection_db=None)
    assert gate.validate_exact_settings(fallback)==result


@pytest.mark.parametrize("field,value",[
    ("ticket_worker_hosting","embedded"),
    ("ticket_worker_hosting","auto"),
    ("autonomy_worker_enabled",False),
    ("autonomy_worker_db",Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")),
    ("autonomy_promotion_db",Path("/var/lib/jason/openclaw/playbook-autonomy.sqlite3")),
    ("autonomy_targeted_wake_db",Path("/var/lib/jason/openclaw/autonomy-targeted-wakes.sqlite3")),
    ("authority_db",Path("/var/lib/jason/openclaw/authority.sqlite3")),
    ("bindings_db",Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")),
    ("orchestration_events_db",Path("/var/lib/jason/openclaw/orchestration-events.sqlite3")),
    ("governed_execution_db",Path("/var/lib/jason/openclaw/governed-execution.sqlite3")),
    ("reflection_db",Path("/var/lib/jason/openclaw/reflection.sqlite3")),
    ("resolution_memory_db",Path("/var/lib/jason/openclaw/resolution-memory.sqlite3")),
    ("microsoft_boundary_db",Path("/tmp/wrong-client-boundaries.sqlite3")),
    ("dnsfilter_mcp_oauth_db",Path("/var/lib/jason/openclaw/dnsfilter-mcp/other.sqlite3")),
    ("quickbooks_oauth_db",Path("/var/lib/jason/openclaw/quickbooks/oauth.sqlite3")),
])
def test_shared_broad_or_wrong_state_path_denied(field,value):
    with pytest.raises(gate.ProjectionDenied,match="CORE_EXACT_"):
        gate.validate_exact_settings(settings(**{field:value}))


def test_readonly_attestation_does_not_issue_authority_or_infer_release():
    seen=gate.validate_exact_mounts(gate.expected_docker_mounts())
    assert seen["root_owner_release_verified"] is False
    expected=gate.validate_exact_settings(settings())
    assert expected["external_worker_ready"] is False
    assert expected["production_mutations"] is False

def test_future_ticket_core_projection_excludes_paid_ai_credentials():
    mounts = list(gate.expected_docker_mounts())
    assert not any("/openbao/openai/" in m["Destination"] for m in mounts)
    mounts.append({"Type":"bind", "Source":"/tmp/old-role",
                   "Destination":"/run/jason-secrets/openbao/openai/role_id", "RW":False})
    with pytest.raises(gate.ProjectionDenied, match="CORE_EXACT_"):
        gate.validate_exact_mounts(mounts)

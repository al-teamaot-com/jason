"""Immutable release-source Owner UAT campaign: no credentials, providers or writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "owner_uat_activation.py"
spec = importlib.util.spec_from_file_location("owner_uat_activation", MODULE)
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)

NOW = datetime(2026, 10, 17, 22, 30, tzinfo=timezone.utc)


def manifest(*, enabled=True):
    return {
        "schema_version": "1.0",
        "enabled": enabled,
        "purpose": "owner_teams_nonexecuting_uat",
        "organization_id": "aot",
        "owner_identity_id": "person-al",
        "requester_identity_id": "svc-jason-acceptance-test",
        "capability": "interaction.owner.acceptance.record",
        "execution_permitted": False,
        "session_id": "OwnerUAT20261017Pilot",
        "expires_at": "2026-10-19T00:00:00Z",
    }


def write(tmp_path, data):
    path = tmp_path / "uat.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_off_by_default_and_preproduction_inert(tmp_path):
    missing = tmp_path / "not-there.json"
    assert activation.activate_from_manifest(missing, now=NOW) == activation.OFF
    bad = write(tmp_path, {"malicious": True})
    assert activation.activate_from_manifest(bad, now=NOW, preflight=True) == activation.OFF
    assert activation.activate_from_manifest(write(tmp_path, manifest(enabled=False)), now=NOW) == activation.OFF


def test_exact_bounded_nonexecuting_campaign(tmp_path):
    path = write(tmp_path, manifest())
    assert activation.activate_from_manifest(path, now=NOW) == (
        "nonexecuting_test_only|true|OwnerUAT20261017Pilot"
    )
    assert activation.activate_from_manifest(path, now=NOW + timedelta(days=2)) == activation.OFF


@pytest.mark.parametrize("change", [
    {"purpose": "release.production.approve"},
    {"capability": "release.production.approve"},
    {"organization_id": "customer"},
    {"owner_identity_id": "person-someone-else"},
    {"requester_identity_id": "person-al"},
    {"execution_permitted": True},
    {"session_id": "123bad"},
    {"session_id": "../../../escape"},
    {"session_id": "X"*120},
    {"expires_at": "2027-01-01T00:00:00Z"},
    {"expires_at": "2026-10-18T10:00:00"},
    {"enabled": "yes"},
    {"schema_version": "2.0"},
    {"unexpected_key": "extra"},
])
def test_unsafe_campaign_rejected(tmp_path, change):
    value = manifest()
    value.update(change)
    with pytest.raises((ValueError, PermissionError)):
        activation.activate_from_manifest(write(tmp_path, value), now=NOW)


def test_symlink_and_writable_source_rejected(tmp_path):
    original = write(tmp_path, manifest())
    link = tmp_path / "link.json"
    link.symlink_to(original)
    with pytest.raises(ValueError, match="regular"):
        activation.activate_from_manifest(link, now=NOW)
    original.chmod(0o666)
    with pytest.raises(PermissionError, match="writable"):
        activation.activate_from_manifest(original, now=NOW)

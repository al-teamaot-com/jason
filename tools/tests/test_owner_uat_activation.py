"""Immutable release-source Owner UAT campaign: no credentials, providers or writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess

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
        "session_id": "OwnerUAT20261018Retry01",
        "expires_at": "2026-10-19T20:00:00Z",
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
        "nonexecuting_test_only|true|OwnerUAT20261018Retry01"
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


def test_git_object_pins_immutable_campaign(tmp_path):
    root = MODULE.parents[1]
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip()
    activation.verify_source_pinned_manifest(root / "config" / "owner-uat-campaign.json", revision)
    with pytest.raises(ValueError, match="exact immutable"):
        activation.verify_source_pinned_manifest(root / "config" / "owner-uat-campaign.json", "bad")
    forged = write(tmp_path, manifest())
    with pytest.raises(PermissionError, match="exact release tree"):
        activation.verify_source_pinned_manifest(forged, revision)



def test_current_committed_nonexecuting_campaign_is_bounded_and_expires():
    """A refreshed campaign must not grant production authority or outlive its window."""
    path = MODULE.parents[1] / "config" / "owner-uat-campaign.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["organization_id"] == "aot"
    assert data["owner_identity_id"] == "person-al"
    assert data["requester_identity_id"] == "svc-jason-acceptance-test"
    assert data["capability"] == "interaction.owner.acceptance.record"
    assert data["execution_permitted"] is False
    assert data["purpose"] == "owner_teams_nonexecuting_uat"
    end = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    assert end.utcoffset() == timedelta(0)
    in_window = end - timedelta(hours=12)
    assert activation.activate_from_manifest(path, now=in_window) == (
        "nonexecuting_test_only|true|" + data["session_id"]
    )
    assert activation.activate_from_manifest(path, now=in_window, preflight=True) == activation.OFF
    assert activation.activate_from_manifest(path, now=end) == activation.OFF
    assert activation.activate_from_manifest(path, now=end + timedelta(seconds=1)) == activation.OFF
    with pytest.raises(ValueError, match="48 hours"):
        activation.activate_from_manifest(path, now=end - timedelta(hours=49))


def test_actual_immutable_release_without_dotgit_uses_exact_managed_git_object(
    monkeypatch, tmp_path
):
    root = MODULE.parents[1]
    sha = subprocess.check_output(
        ["/usr/bin/git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    release_root = tmp_path / "opt" / "jason" / "releases"
    candidate = release_root / sha
    (candidate / "tools").mkdir(parents=True)
    (candidate / "config").mkdir()
    (candidate / "tools" / "owner_uat_activation.py").write_text("# source tested in worktree")
    installed = candidate / "config" / "owner-uat-campaign.json"
    installed.write_bytes((root / "config" / "owner-uat-campaign.json").read_bytes())
    assert not (candidate / ".git").exists()
    monkeypatch.setattr(activation, "__file__",
                        str(candidate / "tools" / "owner_uat_activation.py"))
    monkeypatch.setattr(activation, "IMMUTABLE_RELEASES_ROOT", release_root)
    monkeypatch.setattr(activation, "MANAGED_SOURCE_GIT", root)
    activation.verify_source_pinned_manifest(installed, sha)
    assert activation.activate_from_manifest(
        installed, now=datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    ) == "nonexecuting_test_only|true|OwnerUAT20261023PhaseBound02"

    changed = json.loads(installed.read_text())
    changed["session_id"] = "ForgedOwnerUAT01"
    installed.write_text(json.dumps(changed))
    with pytest.raises(PermissionError, match="differs"):
        activation.verify_source_pinned_manifest(installed, sha)

    installed.write_bytes((root / "config" / "owner-uat-campaign.json").read_bytes())
    with pytest.raises(PermissionError, match="does not belong"):
        activation.verify_source_pinned_manifest(installed, "a" * 40)

    monkeypatch.setattr(activation, "MANAGED_SOURCE_GIT", tmp_path / "not_git")
    with pytest.raises(PermissionError, match="Git object unavailable"):
        activation.verify_source_pinned_manifest(installed, sha)


def test_untrusted_source_without_git_or_immutable_revision_denied(
    monkeypatch, tmp_path
):
    untracked = tmp_path / "untracked"
    (untracked / "tools").mkdir(parents=True)
    (untracked / "config").mkdir()
    src = untracked / "tools" / "owner_uat_activation.py"
    src.write_text("# synthetic")
    f = untracked / "config" / "owner-uat-campaign.json"
    f.write_text(json.dumps(manifest()))
    monkeypatch.setattr(activation, "__file__", str(src))
    with pytest.raises(PermissionError, match="trusted Git"):
        activation.verify_source_pinned_manifest(f, "a" * 40)

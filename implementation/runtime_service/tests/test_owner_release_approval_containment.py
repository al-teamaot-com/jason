"""P0 #1554: one shared, revocation-safe Teams production approval hold.

No provider, production or Teams calls. The safety state file is scoped to the
existing release manager state root; no private approval policy is modified.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest

from jason_runtime.owner_release_approval_containment import (
    HOLD_FILENAME, ReleaseApprovalContainment, read_release_approval_containment,
)

NOW = datetime(2026, 10, 17, 20, 30, tzinfo=timezone.utc)


def safety_file(state_root: Path, *, state: str = "held", when: datetime = NOW,
                released: datetime | None = None) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "capability": "release.production.approve",
        "state": state,
        "hold_id": "P0-1553",
        "hold_started_at": when.isoformat(),
    }
    if released is not None:
        payload["released_at"] = released.isoformat()
    path = state_root / HOLD_FILENAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_absent_record_preserves_existing_governed_owner_flow(tmp_path):
    containment = read_release_approval_containment(tmp_path)
    assert containment.state == "not_configured"
    assert not containment.active
    containment.require_can_issue()
    containment.require_request_eligible(NOW)


def test_durable_hold_blocks_issuance_and_all_old_pending_callbacks(tmp_path):
    safety_file(tmp_path)
    state = read_release_approval_containment(tmp_path)
    assert state.active
    assert state.hold_id == "P0-1553"
    assert not state.is_request_eligible(NOW + timedelta(minutes=1))
    with pytest.raises(PermissionError, match="owner_release_approval_hold_active"):
        state.require_can_issue()
    with pytest.raises(PermissionError, match="hold_active"):
        state.require_request_eligible(NOW)


def test_release_of_hold_revokes_all_preexisting_requests(tmp_path):
    released = NOW + timedelta(minutes=10)
    safety_file(tmp_path, state="released", released=released)
    state = read_release_approval_containment(tmp_path)
    assert not state.active
    state.require_can_issue()
    assert state.hold_started_at == NOW
    for time in (NOW - timedelta(days=1), NOW, NOW + timedelta(minutes=5), released):
        with pytest.raises(PermissionError, match="pre_hold_request_revoked"):
            state.require_request_eligible(time)
    state.require_request_eligible(released + timedelta(microseconds=1))


@pytest.mark.parametrize("bad", [
    {"schema_version":"2.0"},
    {"capability":"service.ticket.update"},
    {"state":"disabled"},
    {"hold_id":"ignore_this_hold"},
    {"hold_started_at":"2026-10-17T16:00:00"},
    {"hold_started_at":"2026-10-17T20:00:00+01:00"},
    {"state":"released"},
    {"released_at":"2026-10-17T20:31:00Z"},
    {"extra":"allows anyone"},
])
def test_insecure_or_malformed_policy_never_silently_activates_approval(tmp_path, bad):
    path = safety_file(tmp_path)
    payload = json.loads(path.read_text())
    payload.update(bad)
    path.write_text(json.dumps(payload))
    with pytest.raises(PermissionError):
        read_release_approval_containment(tmp_path)


def test_nonprivate_policy_and_symlink_fail_closed(tmp_path):
    path = safety_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(PermissionError, match="policy_invalid"):
        read_release_approval_containment(tmp_path)
    path.chmod(0o600)
    path.unlink()
    alternate = tmp_path / "somewhere-else.json"
    alternate.write_text("{}")
    path.symlink_to(alternate)
    with pytest.raises(PermissionError, match="policy_invalid"):
        read_release_approval_containment(tmp_path)


def test_released_policy_has_monotonic_watermark(tmp_path):
    path = safety_file(tmp_path, state="released", released=NOW)
    with pytest.raises(PermissionError, match="after hold"):
        read_release_approval_containment(tmp_path)
    path = safety_file(tmp_path, state="released", released=NOW-timedelta(seconds=1))
    with pytest.raises(PermissionError, match="after hold"):
        read_release_approval_containment(tmp_path)

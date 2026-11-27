"""The new component reader must not replace the historical root trust source."""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import scoped_backport_release_control_transition_worker as worker
from tools import audit_journal_release_scope as audit
from tools import production_freeze_retirement as retirement

ROOT = Path(__file__).resolve().parents[1]
REV = "a"*40


def test_legacy_source_retains_exact_independent_audit_pin():
    legacy = ROOT / "release_control_transition_worker.py"
    successor = ROOT / "scoped_backport_release_control_transition_worker.py"
    assert sha256(legacy.read_bytes()).hexdigest() == audit.PROTECTED[str(audit.ROOT_TRANSITION)]
    assert legacy.read_bytes() != successor.read_bytes()
    assert retirement.SOURCES[retirement.INSTALL/"tools/release_control_transition_worker.py"] == (
        "tools/scoped_backport_release_control_transition_worker.py")


def test_active_component_reader_requires_independent_fingerprint(monkeypatch):
    state = {"host_revision": REV}
    reader = SimpleNamespace(verify_live=Mock(return_value=state),
                             verify_host_fingerprint=Mock())
    monkeypatch.setattr(worker, "coordinated_component_reader", lambda:reader)
    recorded, observed = {"fixture":"recorded"}, {"fixture":"observed"}
    worker.verify_immutable_lkg_fingerprint(recorded, observed)
    reader.verify_host_fingerprint.assert_called_once_with(recorded, observed, state)
    reader.verify_live.return_value=None
    with pytest.raises(ValueError,match="component state disappeared"):
        worker.verify_immutable_lkg_fingerprint(recorded,observed)


@pytest.mark.parametrize("mutation", ["missing","wrong_scope","wrong_revision","incomplete"])
def test_component_health_rejects_unverified_readback(monkeypatch,mutation):
    state={"host_revision":REV}
    reader=SimpleNamespace(verify_live=Mock(return_value=state),digest=Mock(return_value="fixture-digest"))
    monkeypatch.setattr(worker,"coordinated_component_reader",lambda:reader)
    observed={"revision":REV,"complete":True,"coordinated_readback_sha256":"fixture-digest"}
    if mutation=="missing": observed.pop("coordinated_readback_sha256")
    elif mutation=="wrong_scope": observed["coordinated_readback_sha256"]="different"
    elif mutation=="wrong_revision": observed["revision"]="b"*40
    else: observed["complete"]=False
    check=Mock(return_value=json.dumps(observed))
    monkeypatch.setattr(worker.subprocess,"check_output",check)
    with pytest.raises(ValueError,match="production health not verified"):
        worker.verify_health(REV)
    args=check.call_args.args[0]
    assert args[:5]==["runuser","-u","al","--","/usr/bin/python3"]
    assert args[-1]=="--capture-native-health"


def test_legacy_lkg_promotion_remains_denied_in_component_mode(monkeypatch):
    monkeypatch.setattr(worker,"coordinated_component_reader",lambda:object())
    state={"schema_version":"1.0","circuit_breaker":{"state":"closed"}}
    with pytest.raises(ValueError,match="legacy promotion denied"):
        worker.apply_transition({"action":"set_last_known_good","revision":REV},state)
    with pytest.raises(ValueError,match="legacy prior-LKG recovery denied"):
        worker.restore_previous_verified_lkg({"revision":REV},state)

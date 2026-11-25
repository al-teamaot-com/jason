import os
import pytest

from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_ledger import SQLiteImportActivityLedger

DIGEST = "a" * 64
ACTIVITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_claim_persists_across_process_instances(tmp_path):
    path = tmp_path / "cc" / "imports.sqlite3"
    a = SQLiteImportActivityLedger(path)
    a.claim_once(intent_digest=DIGEST)
    b = SQLiteImportActivityLedger(path)
    assert b.read_claim(intent_digest=DIGEST)["state"] == "pending"
    with pytest.raises(ImportAuthorizationError, match="already claimed"):
        b.claim_once(intent_digest=DIGEST)
    b.record_dispatched(intent_digest=DIGEST, activity_id=ACTIVITY)
    assert a.read_claim(intent_digest=DIGEST)["activity_id"] == ACTIVITY
    assert os.stat(path).st_mode & 0o077 == 0


def test_ambiguous_claim_stays_pending_after_restart(tmp_path):
    path = tmp_path / "cc" / "imports.sqlite3"
    SQLiteImportActivityLedger(path).claim_once(intent_digest=DIGEST)
    restarted = SQLiteImportActivityLedger(path)
    assert restarted.read_claim(intent_digest=DIGEST)["activity_id"] is None
    with pytest.raises(ImportAuthorizationError):
        restarted.claim_once(intent_digest=DIGEST)


def test_dispatch_record_cannot_be_overwritten(tmp_path):
    a = SQLiteImportActivityLedger(tmp_path / "cc" / "imports.sqlite3")
    a.claim_once(intent_digest=DIGEST)
    a.record_dispatched(intent_digest=DIGEST, activity_id=ACTIVITY)
    with pytest.raises(ImportAuthorizationError, match="already dispatched"):
        a.record_dispatched(intent_digest=DIGEST, activity_id=ACTIVITY)


def test_symlink_rejected(tmp_path):
    actual = tmp_path / "actual.sqlite3"
    SQLiteImportActivityLedger(actual).claim_once(intent_digest=DIGEST)
    linked = tmp_path / "linked.sqlite3"
    linked.symlink_to(actual)
    with pytest.raises(ImportAuthorizationError, match="symlink"):
        SQLiteImportActivityLedger(linked).read_claim(intent_digest=DIGEST)

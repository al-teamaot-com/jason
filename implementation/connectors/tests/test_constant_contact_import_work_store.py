import os

import pytest

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore

LIST_ID = "11111111-2222-3333-4444-555555555555"
APPROVAL_ID = "planapproval-test-import"


def spec():
    preview = preflight([{
        "email": "one@example.com",
        "marketing_consent": "explicit",
        "consent_evidence": "signed opt-in form",
    }])
    return build_specification(preview, list_ids=[LIST_ID])


def test_work_encrypted_and_bound_once_to_server_plan(tmp_path):
    path = tmp_path / "nested" / "import-work.sqlite3"
    a = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 100)
    work = a.create(
        requester_id="aot-owner", specification=spec(),
        account_binding_sha256="a" * 64,
        suppression_receipt_sha256="b" * 64,
    )
    assert "one@example.com" not in path.read_bytes().decode("latin1")
    assert os.stat(path).st_mode & 0o077 == 0
    b = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 100)
    assert b.load_for_requester(
        work_id=work.work_id, requester_id="aot-owner",
    ).specification == spec()
    bound = b.attach_approval(
        work_id=work.work_id, requester_id="aot-owner",
        approval_id=APPROVAL_ID,
    )
    assert bound.approval_id == APPROVAL_ID
    with pytest.raises(ImportAuthorizationError, match="already bound"):
        b.attach_approval(work_id=work.work_id, requester_id="aot-owner", approval_id=APPROVAL_ID)


def test_cross_user_wrong_key_and_expired_refused(tmp_path):
    path = tmp_path / "work.sqlite3"
    a = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 100)
    work = a.create(
        requester_id="aot-owner", specification=spec(),
        account_binding_sha256="a" * 64, suppression_receipt_sha256="b" * 64,
    )
    with pytest.raises(ImportAuthorizationError, match="owner"):
        a.load_for_requester(work_id=work.work_id, requester_id="wrong")
    with pytest.raises(ImportAuthorizationError, match="unavailable"):
        EncryptedImportWorkStore(
            path, b"B" * 32, clock=lambda: 100,
        ).load_for_requester(work_id=work.work_id, requester_id="aot-owner")
    with pytest.raises(ImportAuthorizationError, match="expired"):
        EncryptedImportWorkStore(
            path, b"A" * 32, clock=lambda: 9999,
        ).load_for_requester(work_id=work.work_id, requester_id="aot-owner")


def test_symlinked_work_db_is_rejected(tmp_path):
    actual = tmp_path / "real.sqlite3"
    store = EncryptedImportWorkStore(actual, b"A" * 32)
    store.create(
        requester_id="aot-owner", specification=spec(),
        account_binding_sha256="a" * 64, suppression_receipt_sha256="b" * 64,
    )
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(actual)
    with pytest.raises(ImportAuthorizationError, match="symlink"):
        EncryptedImportWorkStore(alias, b"A" * 32).create(
            requester_id="aot-owner", specification=spec(),
            account_binding_sha256="a" * 64, suppression_receipt_sha256="b" * 64,
        )


def test_read_only_reconciliation_outlives_short_execution_authority(tmp_path):
    path = tmp_path / "work.sqlite3"
    initial = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 100)
    work = initial.create(
        requester_id="aot-owner", specification=spec(),
        account_binding_sha256="a" * 64,
        suppression_receipt_sha256="b" * 64,
    )
    initial.attach_approval(
        work_id=work.work_id, requester_id="aot-owner",
        approval_id=APPROVAL_ID,
    )
    later = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 4200)
    with pytest.raises(ImportAuthorizationError, match="expired"):
        later.load_for_requester(work_id=work.work_id, requester_id="aot-owner")
    assert later.load_for_reconciliation(
        work_id=work.work_id, requester_id="aot-owner",
    ).approval_id == APPROVAL_ID
    assert len(later.list_reconcilable()) == 1
    exhausted = EncryptedImportWorkStore(path, b"A" * 32, clock=lambda: 200000)
    with pytest.raises(ImportAuthorizationError, match="expired"):
        exhausted.load_for_reconciliation(work_id=work.work_id, requester_id="aot-owner")

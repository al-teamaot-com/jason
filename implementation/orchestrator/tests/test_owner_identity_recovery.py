from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from orchestrator.owner_identity_recovery import (
    RecoveryDenied, apply_recovery, review_recovery,
)

EMAIL = "al_admin@teamaot.com"
TENANT = "11111111-1111-1111-1111-111111111111"
OBJECT = "22222222-2222-2222-2222-222222222222"
SOURCE = "person-entra-" + OBJECT.replace("-", "")
OWNER = "person-al"
OWNERS = frozenset({OWNER})


@pytest.fixture
def sample(tmp_path):
    binding = tmp_path / "bindings.sqlite3"
    authority = tmp_path / "authority.sqlite3"
    with sqlite3.connect(binding) as db:
        db.execute("""CREATE TABLE microsoft_identity_bindings (
          microsoft_tenant_id TEXT, microsoft_object_id TEXT,
          jason_identity_id TEXT, client_id TEXT, email_address TEXT,
          status TEXT, PRIMARY KEY (microsoft_tenant_id, microsoft_object_id))""")
        db.execute("INSERT INTO microsoft_identity_bindings VALUES (?,?,?,?,?,?)",
                   (TENANT, OBJECT, SOURCE, None, EMAIL, "active"))
    with sqlite3.connect(authority) as db:
        db.execute("CREATE TABLE identities(identity_id TEXT PRIMARY KEY,payload TEXT)")
        db.execute("CREATE TABLE authority_grants(grant_id TEXT PRIMARY KEY,subject_id TEXT,payload TEXT)")
        for subject in (SOURCE, OWNER):
            db.execute("INSERT INTO identities VALUES(?,?)", (
                subject, json.dumps(dict(identity_id=subject, identity_type="human",
                                         organization_id="aot", status="active"))))
    return binding, authority, tmp_path / "backup" / "snapshot.sqlite3"


def plan(binding, authority, **kwargs):
    return review_recovery(
        binding_db=binding, authority_db=authority,
        email=kwargs.get("email", EMAIL),
        attested_tenant_id=kwargs.get("tenant", TENANT),
        attested_object_id=kwargs.get("object_id", OBJECT),
        owner_subject=kwargs.get("owner", OWNER),
        live_owner_allowlist=kwargs.get("owners", OWNERS),
    )


def test_review_only_has_no_side_effects(sample):
    binding, authority, backup = sample
    digest = plan(binding, authority).digest
    assert len(digest) == 64
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == SOURCE
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='owner_identity_recovery_audit'").fetchall()
    assert not backup.exists()


@pytest.mark.parametrize("override,code", [
    ({"email": "other@teamaot.com"}, "RECOVERY_EXACT_ONE_ACTIVE_EMAIL_BINDING_REQUIRED"),
    ({"email": "external@example.org"}, "RECOVERY_AOT_EMAIL_REQUIRED"),
    ({"tenant": "33333333-3333-3333-3333-333333333333"}, "RECOVERY_INDEPENDENT_ENTRA_ATTESTATION_MISMATCH"),
    ({"object_id": "33333333-3333-3333-3333-333333333333"}, "RECOVERY_INDEPENDENT_ENTRA_ATTESTATION_MISMATCH"),
    ({"owners": frozenset()}, "RECOVERY_NOT_IN_LIVE_OWNER_ALLOWLIST"),
    ({"owner": "person-unknown"}, "RECOVERY_NOT_IN_LIVE_OWNER_ALLOWLIST"),
])
def test_review_fail_closed(sample, override, code):
    with pytest.raises(RecoveryDenied, match=code):
        plan(*sample[:2], **override)


def test_review_denies_existing_owner_binding(sample):
    binding, authority, _ = sample
    with sqlite3.connect(binding) as db:
        db.execute("INSERT INTO microsoft_identity_bindings VALUES (?,?,?,?,?,?)",
                   (TENANT, "44444444-4444-4444-4444-444444444444", OWNER, None,
                    "other@teamaot.com", "active"))
    with pytest.raises(RecoveryDenied, match="RECOVERY_OWNER_ALREADY_BOUND"):
        plan(binding, authority)


def test_review_denies_scoped_binding(sample):
    binding, authority, _ = sample
    with sqlite3.connect(binding) as db:
        db.execute("UPDATE microsoft_identity_bindings SET client_id='1158'")
    with pytest.raises(RecoveryDenied, match="RECOVERY_CLIENT_SCOPED_BINDING_DENIED"):
        plan(binding, authority)


def test_review_denies_source_with_execute_grant(sample):
    binding, authority, _ = sample
    with sqlite3.connect(authority) as db:
        db.execute("INSERT INTO authority_grants VALUES (?,?,?)",
                   ("grant-1", SOURCE, json.dumps({"grant_id": "grant-1", "status": "active", "permission": "execute"})))
    with pytest.raises(RecoveryDenied, match="RECOVERY_SOURCE_HAS_EXECUTE_OR_ADMINISTER_GRANT"):
        plan(binding, authority)


def test_review_denies_inactive_source_and_owner(sample):
    binding, authority, _ = sample
    with sqlite3.connect(authority) as db:
        db.execute("UPDATE identities SET payload=? WHERE identity_id=?",
                   (json.dumps(dict(identity_id=OWNER, identity_type="human",
                                    organization_id="aot", status="disabled")), OWNER))
    with pytest.raises(RecoveryDenied, match="RECOVERY_IDENTITY_NOT_ACTIVE_AOT_HUMAN"):
        plan(binding, authority)


def test_exact_recovery_commits_single_row_and_immutable_audit(sample):
    binding, authority, backup = sample
    review = plan(binding, authority)
    event = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=review, live_owner_allowlist=OWNERS,
        approval_reference="AOT-OWNER-RECOVERY-TEST",
        operator_account="al",
        backup_path=backup,
    )
    assert event.startswith("owner-recovery-")
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == OWNER
        assert db.execute("SELECT count(*) FROM owner_identity_recovery_audit").fetchone()[0] == 1
        row = db.execute("SELECT review_digest, approval_reference, operator_account FROM owner_identity_recovery_audit").fetchone()
        assert row == (review.digest, "AOT-OWNER-RECOVERY-TEST", "al")
        with pytest.raises(sqlite3.IntegrityError, match="immutable_audit"):
            db.execute("DELETE FROM owner_identity_recovery_audit")
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == SOURCE
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_state_change_denies_and_preserves_source(sample):
    binding, authority, backup = sample
    review = plan(binding, authority)
    with sqlite3.connect(authority) as db:
        db.execute("UPDATE identities SET payload=? WHERE identity_id=?", (
            json.dumps(dict(identity_id=OWNER, identity_type="human",
                            organization_id="aot", status="disabled")), OWNER))
    with pytest.raises(RecoveryDenied, match="RECOVERY_IDENTITY_NOT_ACTIVE_AOT_HUMAN"):
        apply_recovery(
            binding_db=binding, authority_db=authority,
            review=review, live_owner_allowlist=OWNERS,
            approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup,
        )
    assert not backup.exists()
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == SOURCE


def test_existing_backup_denies_without_mutation(sample):
    binding, authority, backup = sample
    review = plan(binding, authority)
    backup.parent.mkdir()
    backup.write_text("do not overwrite")
    with pytest.raises(RecoveryDenied, match="RECOVERY_BACKUP_ALREADY_EXISTS"):
        apply_recovery(
            binding_db=binding, authority_db=authority, review=review,
            live_owner_allowlist=OWNERS, approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup,
        )
    assert backup.read_text() == "do not overwrite"


def test_second_apply_is_denied_not_duplicate(sample):
    binding, authority, backup = sample
    review = plan(binding, authority)
    apply_recovery(
        binding_db=binding, authority_db=authority, review=review,
        live_owner_allowlist=OWNERS, approval_reference="AOT-OWNER-RECOVERY-TEST",
        operator_account="al", backup_path=backup,
    )
    with pytest.raises(RecoveryDenied):
        apply_recovery(
            binding_db=binding, authority_db=authority, review=review,
            live_owner_allowlist=OWNERS, approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup.parent / "second.sqlite3",
        )
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT count(*) FROM owner_identity_recovery_audit").fetchone()[0] == 1


def test_rollback_is_exact_one_row_audited_and_backed_up(sample):
    from orchestrator.owner_identity_recovery import review_rollback, apply_rollback

    binding, authority, first_backup = sample
    recovered = plan(binding, authority)
    event = apply_recovery(
        binding_db=binding, authority_db=authority, review=recovered,
        live_owner_allowlist=OWNERS, approval_reference="AOT-OWNER-RECOVERY-TEST",
        operator_account="al", backup_path=first_backup,
    )
    rollback = review_rollback(
        binding_db=binding, authority_db=authority, email=EMAIL,
        attested_tenant_id=TENANT, attested_object_id=OBJECT,
        owner_subject=OWNER, original_event_id=event,
        live_owner_allowlist=OWNERS,
    )
    revert_backup = first_backup.parent / "before-rollback.sqlite3"
    revert_event = apply_rollback(
        binding_db=binding, authority_db=authority, review=rollback,
        live_owner_allowlist=OWNERS,
        approval_reference="AOT-OWNER-ROLLBACK-TEST",
        operator_account="al", backup_path=revert_backup,
    )
    assert revert_event.startswith("owner-recovery-revert-")
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == SOURCE
        actions = db.execute("SELECT action FROM owner_identity_recovery_audit ORDER BY occurred_at").fetchall()
        assert sorted(x[0] for x in actions) == ["recover", "rollback"]
        with pytest.raises(sqlite3.IntegrityError, match="immutable_audit"):
            db.execute("DELETE FROM owner_identity_recovery_audit")
    with sqlite3.connect(revert_backup) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == OWNER
    with pytest.raises(RecoveryDenied):
        review_rollback(
            binding_db=binding, authority_db=authority, email=EMAIL,
            attested_tenant_id=TENANT, attested_object_id=OBJECT,
            owner_subject=OWNER, original_event_id=event,
            live_owner_allowlist=OWNERS,
        )


def test_rollback_wrong_event_or_wrong_oid_denied(sample):
    from orchestrator.owner_identity_recovery import review_rollback

    binding, authority, backup = sample
    recovered = plan(binding, authority)
    event = apply_recovery(
        binding_db=binding, authority_db=authority, review=recovered,
        live_owner_allowlist=OWNERS, approval_reference="AOT-OWNER-RECOVERY-TEST",
        operator_account="al", backup_path=backup,
    )
    for event_id, oid in [
        ("owner-recovery-unrelated", OBJECT),
        (event, "33333333-3333-3333-3333-333333333333"),
    ]:
        with pytest.raises(RecoveryDenied, match="ROLLBACK_ORIGINAL_EVENT_ATTESTATION_MISMATCH"):
            review_rollback(
                binding_db=binding, authority_db=authority, email=EMAIL,
                attested_tenant_id=TENANT, attested_object_id=oid,
                owner_subject=OWNER, original_event_id=event_id,
                live_owner_allowlist=OWNERS,
            )


def test_failed_audit_insert_rolls_back_identity_change(sample, monkeypatch):
    import uuid
    from orchestrator import owner_identity_recovery as recovery

    binding, authority, backup = sample
    recovered = plan(binding, authority)
    fake = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    with sqlite3.connect(binding) as db:
        db.executescript(recovery._AUDIT_SCHEMA)
        db.execute(
            "INSERT INTO owner_identity_recovery_audit("
            "event_id,occurred_at,email,tenant_id,object_id,from_subject,"
            "to_subject,review_digest,approval_reference,operator_account,action)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("owner-recovery-" + fake.hex, "2026-11-07T00:00:00+00:00",
             EMAIL, TENANT, OBJECT, SOURCE, OWNER, recovered.digest,
             "AOT-OLD-EVENT", "al", "recover"),
        )
    monkeypatch.setattr(recovery, "uuid4", lambda: fake)
    with pytest.raises(sqlite3.IntegrityError):
        apply_recovery(
            binding_db=binding, authority_db=authority, review=recovered,
            live_owner_allowlist=OWNERS,
            approval_reference="AOT-OWNER-RECOVERY-TEST", operator_account="al",
            backup_path=backup,
        )
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == SOURCE
        assert db.execute("SELECT count(*) FROM owner_identity_recovery_audit").fetchone()[0] == 1


def test_concurrent_binding_change_after_backup_does_not_create_audit_schema(sample, monkeypatch):
    from orchestrator import owner_identity_recovery as recovery

    binding, authority, backup = sample
    reviewed = plan(binding, authority)
    original_backup = recovery._take_verified_backup

    def switched_after_backup(db_path, out_path):
        original_backup(db_path, out_path)
        with sqlite3.connect(binding) as db:
            db.execute(
                "UPDATE microsoft_identity_bindings SET jason_identity_id='other-principal'"
            )

    monkeypatch.setattr(recovery, "_take_verified_backup", switched_after_backup)
    with pytest.raises(RecoveryDenied, match="RECOVERY_CONCURRENT_BINDING_CHANGE"):
        recovery.apply_recovery(
            binding_db=binding, authority_db=authority, review=reviewed,
            live_owner_allowlist=OWNERS,
            approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup,
        )
    with sqlite3.connect(binding) as db:
        assert db.execute("SELECT jason_identity_id FROM microsoft_identity_bindings").fetchone()[0] == "other-principal"
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='owner_identity_recovery_audit'").fetchone()[0] == 0
    assert backup.exists()



def test_old_recovery_event_cannot_authorize_rollback_of_newer_recovery(sample):
    from orchestrator.owner_identity_recovery import review_rollback, apply_rollback

    binding, authority, first_backup = sample
    first = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=plan(binding, authority), live_owner_allowlist=OWNERS,
        approval_reference="AOT-OWNER-FIRST-TEST", operator_account="al",
        backup_path=first_backup,
    )
    rollback_plan = review_rollback(
        binding_db=binding, authority_db=authority, email=EMAIL,
        attested_tenant_id=TENANT, attested_object_id=OBJECT,
        owner_subject=OWNER, original_event_id=first,
        live_owner_allowlist=OWNERS,
    )
    apply_rollback(
        binding_db=binding, authority_db=authority, review=rollback_plan,
        live_owner_allowlist=OWNERS, approval_reference="AOT-FIRST-ROLLBACK",
        operator_account="al",
        backup_path=first_backup.parent / "second-backup.sqlite3",
    )
    second = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=plan(binding, authority), live_owner_allowlist=OWNERS,
        approval_reference="AOT-OWNER-SECOND-TEST", operator_account="al",
        backup_path=first_backup.parent / "third-backup.sqlite3",
    )
    assert second != first
    with pytest.raises(
        RecoveryDenied, match="ROLLBACK_ORIGINAL_RECOVERY_NOT_LATEST_EVENT"
    ):
        review_rollback(
            binding_db=binding, authority_db=authority, email=EMAIL,
            attested_tenant_id=TENANT, attested_object_id=OBJECT,
            owner_subject=OWNER, original_event_id=first,
            live_owner_allowlist=OWNERS,
        )
    second_rollback = review_rollback(
        binding_db=binding, authority_db=authority, email=EMAIL,
        attested_tenant_id=TENANT, attested_object_id=OBJECT,
        owner_subject=OWNER, original_event_id=second,
        live_owner_allowlist=OWNERS,
    )
    assert second_rollback.original_event_id == second
    with sqlite3.connect(binding) as db:
        trace = db.execute(
            "SELECT related_event_id FROM owner_identity_recovery_audit "
            "WHERE action='rollback'"
        ).fetchall()
        assert trace == [(first,)]


def test_original_approval_reference_cannot_be_replayed_after_rollback(sample):
    from orchestrator.owner_identity_recovery import review_rollback, apply_rollback

    binding, authority, original_backup = sample
    original = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=plan(binding, authority), live_owner_allowlist=OWNERS,
        approval_reference="OWNER-APPROVED-ONCE", operator_account="al",
        backup_path=original_backup,
    )
    undo = review_rollback(
        binding_db=binding, authority_db=authority, email=EMAIL,
        attested_tenant_id=TENANT, attested_object_id=OBJECT,
        owner_subject=OWNER, original_event_id=original,
        live_owner_allowlist=OWNERS,
    )
    apply_rollback(
        binding_db=binding, authority_db=authority, review=undo,
        live_owner_allowlist=OWNERS,
        approval_reference="OWNER-APPROVED-UNDO", operator_account="al",
        backup_path=original_backup.parent / "undo.sqlite3",
    )
    with pytest.raises(RecoveryDenied, match="RECOVERY_APPROVAL_REFERENCE_ALREADY_USED"):
        apply_recovery(
            binding_db=binding, authority_db=authority,
            review=plan(binding, authority), live_owner_allowlist=OWNERS,
            approval_reference="OWNER-APPROVED-ONCE", operator_account="al",
            backup_path=original_backup.parent / "reused.sqlite3",
        )
    with sqlite3.connect(binding) as db:
        assert db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings"
        ).fetchone()[0] == SOURCE


@pytest.mark.parametrize("email", [
    "al_admin@@teamaot.com",
    "hello world@teamaot.com",
    "al_admin@teamaot.com@example.com",
])
def test_malformed_aot_email_denied(sample, email):
    with pytest.raises(RecoveryDenied, match="RECOVERY_AOT_EMAIL_REQUIRED"):
        plan(*sample[:2], email=email)


@pytest.mark.parametrize("uuid", [
    "111111111111111111111111111111111111",
    "zzzzzzzz-1111-1111-1111-111111111111",
    "1" * 35 + "-",
])
def test_invalid_entr_uuid_denied(sample, uuid):
    with pytest.raises(RecoveryDenied, match="RECOVERY_ATTESTED_ENTRA_UUID_REQUIRED"):
        plan(*sample[:2], tenant=uuid)


def test_recovery_blocks_concurrent_authority_writers_while_binding_lock_held(sample):
    from orchestrator.owner_identity_recovery import _locked_recovery_connection

    binding, authority, _ = sample
    db = _locked_recovery_connection(
        binding_db=binding, authority_db=authority,
    )
    try:
        competing = sqlite3.connect(authority, timeout=0.01)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competing.execute(
                    "INSERT INTO authority_grants VALUES(?,?,?)",
                    ("late-grant", SOURCE, '{"status":"active","permission":"execute"}'),
                )
                competing.commit()
        finally:
            competing.rollback()
            competing.close()
    finally:
        db.execute("ROLLBACK")
        db.close()


def test_recovery_denies_if_source_is_promoted_after_backup(sample, monkeypatch):
    from orchestrator import owner_identity_recovery as recovery

    binding, authority, backup = sample
    reviewed = plan(binding, authority)
    original_backup = recovery._take_verified_backup

    def promote_source_after_backup(db_path, out_path):
        original_backup(db_path, out_path)
        with sqlite3.connect(authority) as db:
            db.execute("INSERT INTO authority_grants VALUES(?,?,?)",
                       ("late-grant", SOURCE,
                        json.dumps({"grant_id":"late-grant","status":"active",
                                    "permission":"execute"})))

    monkeypatch.setattr(recovery, "_take_verified_backup", promote_source_after_backup)
    with pytest.raises(
        RecoveryDenied, match="RECOVERY_SOURCE_HAS_EXECUTE_OR_ADMINISTER_GRANT"
    ):
        apply_recovery(
            binding_db=binding, authority_db=authority,
            review=reviewed, live_owner_allowlist=OWNERS,
            approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup,
        )
    with sqlite3.connect(binding) as db:
        assert db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings"
        ).fetchone()[0] == SOURCE


def test_high_risk_apply_denies_wal_authority_mode_without_safe_locking(sample):
    binding, authority, backup = sample
    with sqlite3.connect(authority) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    with pytest.raises(RecoveryDenied, match="RECOVERY_UNSAFE_AUTHORITY_JOURNAL_MODE"):
        apply_recovery(
            binding_db=binding, authority_db=authority,
            review=plan(binding, authority),
            live_owner_allowlist=OWNERS,
            approval_reference="AOT-OWNER-RECOVERY-TEST",
            operator_account="al", backup_path=backup,
        )
    with sqlite3.connect(binding) as db:
        assert db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings"
        ).fetchone()[0] == SOURCE


def test_audit_evidence_sha_can_be_externally_archived(sample):
    from orchestrator.owner_identity_recovery import recovery_audit_evidence_sha256

    binding, authority, backup = sample
    event = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=plan(binding, authority), live_owner_allowlist=OWNERS,
        approval_reference="AUDIT-EVIDENCE-CHANGE",
        operator_account="al", backup_path=backup,
    )
    digest = recovery_audit_evidence_sha256(binding_db=binding, event_id=event)
    assert len(digest) == 64
    assert digest == recovery_audit_evidence_sha256(
        binding_db=binding, event_id=event,
    )
    with pytest.raises(RecoveryDenied, match="RECOVERY_AUDIT_EVENT_MISSING"):
        recovery_audit_evidence_sha256(
            binding_db=binding, event_id="not-a-real-event",
        )


def test_rollback_denies_if_source_promoted_after_backup(sample, monkeypatch):
    from orchestrator import owner_identity_recovery as recovery

    binding, authority, initial_backup = sample
    event = apply_recovery(
        binding_db=binding, authority_db=authority,
        review=plan(binding, authority),
        live_owner_allowlist=OWNERS,
        approval_reference="OWNER-RECOVERY-FIRST",
        operator_account="al", backup_path=initial_backup,
    )
    rollback_review = recovery.review_rollback(
        binding_db=binding, authority_db=authority,
        email=EMAIL, attested_tenant_id=TENANT, attested_object_id=OBJECT,
        owner_subject=OWNER, original_event_id=event,
        live_owner_allowlist=OWNERS,
    )
    original_backup = recovery._take_verified_backup

    def promote_source_after_backup(db_path, out_path):
        original_backup(db_path, out_path)
        with sqlite3.connect(authority) as db:
            db.execute(
                "INSERT INTO authority_grants VALUES(?,?,?)",
                ("late-execute-grant", SOURCE, json.dumps({
                    "grant_id": "late-execute-grant",
                    "status": "active", "permission": "execute",
                })),
            )

    monkeypatch.setattr(recovery, "_take_verified_backup", promote_source_after_backup)
    with pytest.raises(RecoveryDenied, match="ROLLBACK_SOURCE_NOT_READ_ONLY"):
        recovery.apply_rollback(
            binding_db=binding, authority_db=authority,
            review=rollback_review, live_owner_allowlist=OWNERS,
            approval_reference="OWNER-ROLLBACK-REVIEW",
            operator_account="al",
            backup_path=initial_backup.parent / "rollback-backup.sqlite3",
        )
    with sqlite3.connect(binding) as db:
        assert db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings"
        ).fetchone()[0] == OWNER
        assert db.execute(
            "SELECT count(*) FROM owner_identity_recovery_audit"
        ).fetchone()[0] == 1

"""No external provider requests: verify independent read-only queue behavior."""
from types import SimpleNamespace

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_ledger import SQLiteImportActivityLedger
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore
from connectors.constant_contact.import_reconcile import ConstantContactReadbackWorker
from connectors.constant_contact.governed_import import intent_for_work

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACTIVITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def create_work(work_store, claims, *, index, dispatched=True):
    p = preflight([{
        "email": f"person{index}@example.com",
        "marketing_consent": "explicit",
        "consent_evidence": f"opt-in {index}",
    }])
    spec = build_specification(p, list_ids=[LIST_ID])
    work = work_store.create(
        requester_id="aot-owner", specification=spec,
        account_binding_sha256="a" * 64,
        suppression_receipt_sha256="b" * 64,
    )
    bound = work_store.attach_approval(
        work_id=work.work_id, requester_id="aot-owner",
        approval_id=f"planapproval-{index}",
    )
    if dispatched:
        claim = intent_for_work(bound).digest()
        claims.claim_once(intent_digest=claim)
        claims.record_dispatched(intent_digest=claim, activity_id=ACTIVITY)
    return bound


class FakeReadback:
    def __init__(self):
        self.calls = []

    def reconcile(self, *, work_id, requester_id):
        self.calls.append((work_id, requester_id))
        if len(self.calls) == 1:
            raise ConnectionError("private token should not escape")
        return {"status": "verified"}


def test_unrelated_jobs_continue_despite_first_provider_failure(tmp_path):
    store = EncryptedImportWorkStore(tmp_path / "work.db", b"A" * 32)
    claims = SQLiteImportActivityLedger(tmp_path / "claims.db")
    first = create_work(store, claims, index=1)
    second = create_work(store, claims, index=2)
    create_work(store, claims, index=3, dispatched=False)
    fake = FakeReadback()
    cycle = ConstantContactReadbackWorker(
        work_store=store, claims=claims, connector=fake,
    ).run_once(max_items=10)
    assert cycle.considered == 2
    assert cycle.verified == 1
    assert cycle.pending == 0
    assert cycle.blocked == 1
    assert cycle.reasons == ("import_readback_failed",)
    assert fake.calls == [(first.work_id, "aot-owner"), (second.work_id, "aot-owner")]


def test_unapproved_or_unclaimed_work_not_auto_dispatched(tmp_path):
    store = EncryptedImportWorkStore(tmp_path / "work.db", b"A" * 32)
    claims = SQLiteImportActivityLedger(tmp_path / "claims.db")
    create_work(store, claims, index=1, dispatched=False)
    fake = FakeReadback()
    cycle = ConstantContactReadbackWorker(
        work_store=store, claims=claims, connector=fake,
    ).run_once()
    assert cycle.considered == 0
    assert fake.calls == []

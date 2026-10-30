from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from autonomous_remediation.autonomous_queue_worker import QueueCandidate
from jason_runtime.nonactionable_ticket_cleanup import (
    classify, identity_ready, only_system_notes,
)
from jason_runtime.autonomy_worker_runtime import (
    NONACTIONABLE_CLEANUP_SCOPE,
    OperationalAutonomyMaintenance,
    SQLiteOperationalWorkStore,
)


def vendor_offer():
    return {
        "id": 143268,
        "ticketNumber": "T20261028.0011",
        "title": "A scary-good 50% off Hosting ??",
        "description": 'From "Network Solutions" <info@eml.networksolutions.com>: '
                       'Save 50% on hosting for a limited time. Get 50% off.',
        "source": 4,
        "status": 1,
        "queueID": 29682833,
        "companyID": 1162,
        "companyLocationID": 990,
        "configurationItemID": None,
    }


def test_strict_classification_accepts_original_two_offers():
    t = vendor_offer()
    assert classify(t).category == "verified_vendor_promotion"
    t["title"] = "Take 20% off your next domain"
    assert classify(t).category == "verified_vendor_promotion"


def test_out_of_office_reply_without_device_is_supported():
    t = vendor_offer()
    t["title"] = "Automatic reply: training course"
    t["description"] = "Thank you for your email. I'm out of the office on vacation."
    assert classify(t).category == "out_of_office_auto_reply"
    assert identity_ready(t)


def test_ambiguous_mail_and_operational_reports_never_complete():
    t = vendor_offer()
    for title in (
        "Security alert: 50% off", "Invoice - 50% off", "Thank You for Your Payment",
        "All Organizations Backup Success Report - Datto SaaS Protection",
        "Your license renewal: 50% off",
    ):
        t["title"] = title
        assert classify(t) is None, title
    t["title"] = "50% off Hosting"
    t["source"] = 8
    assert classify(t) is None
    t["source"] = 4
    t["description"] = 'From "Client" <user@customer.test>: 50% off hosting'
    assert classify(t) is None
    t["description"] = 'From "Network Solutions" <info@eml.networksolutions.com>: T20261029.0037'
    assert classify(t) is None


def test_site_is_mandatory_user_and_device_are_not():
    t = vendor_offer()
    assert identity_ready(t)
    for attr in ("companyID", "companyLocationID"):
        u = dict(t, **{attr: None})
        assert not identity_ready(u)
    assert not identity_ready(dict(t, configurationItemID=1626))
    assert only_system_notes([{"creatorResourceID": 4, "noteType": 13, "createdByContactID": None}])
    assert not only_system_notes([{"creatorResourceID": 1001, "noteType": 3, "createdByContactID": None}])
    assert not only_system_notes([{"creatorResourceID": 4, "noteType": 13, "createdByContactID": 22}])


class ReadPort:
    def __init__(self, ticket, *, human_note=False, time_entry=False):
        self.ticket = ticket
        self.notes = (
            [{"creatorResourceID": 29682899, "noteType": 3,
              "title": "Technician response", "createdByContactID": None}]
            if human_note else
            [{"creatorResourceID": 4, "noteType": 13,
              "title": "Workflow Rule Fired", "createdByContactID": None}]
        )
        self.calls = []
        self.time_entries = [{"id": 8201}] if time_entry else []

    def execute(self, capability, arguments):
        self.calls.append((capability, deepcopy(arguments)))
        if capability == "service.ticket.time.entry.search":
            data = {"items": deepcopy(self.time_entries)}
        elif capability == "service.ticket.read":
            data = {"items": [deepcopy(self.ticket)]}
        elif capability == "service.company.read":
            data = {"item": {"id": 1162, "companyName": "Atlantic Office Technologies",
                             "isActive": True}}
        elif capability == "service.ticket.notes.search":
            data = {"items": deepcopy(self.notes)}
        else:
            raise AssertionError(f"unexpected read {capability}")
        return {"status": "succeeded", "evidence": {"data": data}}


class Actions:
    def __init__(self, reads):
        self.reads = reads
        self.calls = []

    def execute(self, scope, capability, arguments):
        self.calls.append((scope.playbook_id, capability, deepcopy(arguments)))
        payload = arguments["payload"]
        if capability == "service.ticket.update":
            if "status" in payload:
                self.reads.ticket["status"] = {
                    "In Progress": 8, "Complete": 5,
                }[payload["status"]]
            if "queueID" in payload:
                self.reads.ticket["queueID"] = 29683489
            return {"data": {"jasonVerification": {
                "readbackVerified": True,
                "verifiedFields": list(payload.keys()),
            }}}
        if capability == "service.ticket.note.create":
            self.reads.notes.append({
                "creatorResourceID": 29682899, "noteType": 3,
                "title": payload["title"], "createdByContactID": None,
            })
            return {"status": "succeeded"}
        raise AssertionError("unexpected action " + capability)


class Promotions:
    def __init__(self, enabled):
        self.enabled = enabled

    def find_scope_approved(self, **kwargs):
        if self.enabled and kwargs["playbook_id"] == NONACTIONABLE_CLEANUP_SCOPE.playbook_id:
            return {"approval_id": "owner-exact-test"}
        return None


class Source:
    def __init__(self, ticket):
        self.ticket = ticket

    def _required_queue_id(self, name):
        assert name == "Jason"
        return 29683489

    def reconcile_candidates(self):
        return (QueueCandidate(
            resource_id=str(self.ticket["id"]),
            priority=1, source_queue="Help Desk I",
            source_version="snapshot-1", context={
                **deepcopy(self.ticket),
                "_jason_source_status_label": "New",
                "_jason_assigned_elsewhere": True,
            },
        ),)


def build_worker(tmp_path, *, promoted=True, ticket=None, human_note=False, time_entry=False):
    ticket = deepcopy(ticket or vendor_offer())
    reads = ReadPort(ticket, human_note=human_note, time_entry=time_entry)
    actions = Actions(reads)
    store = SQLiteOperationalWorkStore(tmp_path / "operational.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=Source(ticket),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=Promotions(promoted),
        monotonic=lambda: 1000,
    )
    return worker, actions, store


def test_owner_promoted_administrative_cleanup_end_to_end(tmp_path):
    worker, actions, store = build_worker(tmp_path)
    worker.tick()
    assert [x[1] for x in actions.calls] == [
        "service.ticket.update", "service.ticket.note.create", "service.ticket.update",
    ]
    claim = actions.calls[0][2]["payload"]
    assert claim == {"id": 143268, "queueID": "Jason", "status": "In Progress"}
    note = actions.calls[1][2]["payload"]
    assert note["publish"] == 2 and note["noteType"] == 3
    assert "companyLocationID=990" in note["description"]
    assert "completion pending" in note["description"].casefold()
    assert "ticket completed" not in note["description"].casefold()
    assert actions.calls[-1][2]["payload"] == {"id": 143268, "status": "Complete"}
    assert store.get(143268).phase == "complete"
    worker._next_due = 0
    worker.tick()
    assert len(actions.calls) == 3  # no duplicate terminal completion


def test_unpromoted_playbook_has_zero_writes(tmp_path):
    worker, actions, store = build_worker(tmp_path, promoted=False)
    worker.tick()
    assert actions.calls == []
    assert store.get(143268) is None


def test_no_site_fails_closed_without_claim(tmp_path):
    ticket = vendor_offer()
    ticket["companyLocationID"] = None
    worker, actions, store = build_worker(tmp_path, ticket=ticket)
    worker.tick()
    assert actions.calls == []
    assert store.get(143268) is None


def test_human_activity_fails_closed_without_claim(tmp_path):
    worker, actions, store = build_worker(tmp_path, human_note=True)
    worker.tick()
    assert actions.calls == []
    assert store.get(143268) is None


def test_auto_reply_can_complete_without_user_or_device(tmp_path):
    t = vendor_offer()
    t["title"] = "Automatic reply: training course"
    t["description"] = "Thank you for your email. I will be out of the office on vacation."
    worker, actions, store = build_worker(tmp_path, ticket=t)
    worker.tick()
    assert store.get(143268).phase == "complete"
    assert "out_of_office_auto_reply" in actions.calls[1][2]["payload"]["description"]


def test_site_drift_after_claim_blocks_completion(tmp_path):
    worker, actions, store = build_worker(tmp_path)
    update = actions.execute

    def drift_after_claim(scope, capability, arguments):
        result = update(scope, capability, arguments)
        if capability == "service.ticket.update" and arguments["payload"].get("status") == "In Progress":
            actions.reads.ticket["companyLocationID"] = 991
        return result

    actions.execute = drift_after_claim
    worker.tick()
    assert store.get(143268).phase != "complete"
    assert not any(
        c == "service.ticket.update" and a["payload"].get("status") == "Complete"
        for _, c, a in actions.calls
    )


def test_unverified_completion_response_never_marks_worker_complete(tmp_path):
    worker, actions, store = build_worker(tmp_path)
    update = actions.execute

    def completion_without_readback(scope, capability, arguments):
        result = update(scope, capability, arguments)
        if capability == "service.ticket.update" and arguments["payload"].get("status") == "Complete":
            result["data"]["jasonVerification"]["readbackVerified"] = False
        return result

    actions.execute = completion_without_readback
    worker.tick()
    assert store.get(143268).phase != "complete"



def test_existing_technician_time_entry_never_autocompletes(tmp_path):
    worker, actions, store = build_worker(tmp_path, time_entry=True)
    worker.tick()
    assert actions.calls == []
    assert store.get(143268) is None


def test_client_reply_between_internal_note_and_completion_blocks_closure(tmp_path):
    worker, actions, store = build_worker(tmp_path)
    original_execute = actions.execute

    def inject_client_reply(scope, capability, arguments):
        response = original_execute(scope, capability, arguments)
        if (capability == "service.ticket.note.create"
                and arguments["payload"].get("title")
                    == "Jason - Non-Actionable Ticket Cleanup - Resolution"):
            actions.reads.notes.append({
                "creatorResourceID": 9901, "noteType": 3,
                "title": "Client asks for support", "createdByContactID": 53,
            })
        return response

    actions.execute = inject_client_reply
    worker.tick()
    assert store.get(143268).phase != "complete"
    assert not any(
        cap == "service.ticket.update" and payload["payload"].get("status") == "Complete"
        for _, cap, payload in actions.calls
    )


def test_missing_internal_note_readback_blocks_closure(tmp_path):
    worker, actions, store = build_worker(tmp_path)
    original_execute = actions.execute

    def lose_note_visibility(scope, capability, arguments):
        response = original_execute(scope, capability, arguments)
        if (capability == "service.ticket.note.create"
                and arguments["payload"].get("title")
                    == "Jason - Non-Actionable Ticket Cleanup - Resolution"):
            actions.reads.notes = [
                n for n in actions.reads.notes
                if n.get("title") != "Jason - Non-Actionable Ticket Cleanup - Resolution"
            ]
        return response

    actions.execute = lose_note_visibility
    worker.tick()
    assert store.get(143268).phase != "complete"
    assert not any(
        cap == "service.ticket.update" and payload["payload"].get("status") == "Complete"
        for _, cap, payload in actions.calls
    )

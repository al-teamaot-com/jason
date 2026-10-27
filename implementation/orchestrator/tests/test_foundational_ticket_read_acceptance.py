from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json

import pytest

from orchestrator.foundational_ticket_read_acceptance import (
    TicketReadCanaryError,
    run_ticket_read_canary,
)

CANDIDATE = "a" * 40
BASELINE = "b" * 40
NOW = datetime(2026, 10, 27, 13, 30, tzinfo=timezone.utc)
START = "2026-10-27T00:00:00Z"
END = "2026-10-27T11:30:00Z"


class GovernedReadFixture:
    """Test port only, NOT an authority-grant substitute."""

    def __init__(self, *, count=9, ids=None, read_id=None,
                 failed_capability=None, response_provider="autotask"):
        self.count = count
        self.ids = list(range(101, 110)) if ids is None else list(ids)
        self.read_id = read_id
        self.failed_capability = failed_capability
        self.provider = response_provider
        self.calls = []

    def __call__(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == self.failed_capability:
            return self.response(capability, {}, status="denied",
                                 error_code="INFORMATION_RELEASE_DENIED")
        if capability == "service.ticket.count":
            return self.response(capability, {"queryCount": self.count})
        if capability == "service.ticket.search":
            cursor = arguments.get("after_resource_id", 0)
            selected = [n for n in self.ids if n > cursor]
            selected = selected[:arguments["page_size"]]
            return self.response(capability, {
                "items": [{"id": x, "description": "SECRET-CUSTOMER-DATA"}
                          for x in selected]
            })
        if capability == "service.ticket.read":
            returned_id = (self.read_id if self.read_id is not None
                           else arguments["resource_id"])
            return self.response(capability, {
                "items": [{"id": returned_id,
                           "description": "SECRET-CUSTOMER-DATA",
                           "email": "private@example.invalid"}]
            })
        raise AssertionError("unexpected capability")

    def response(self, cap, data, *, status="succeeded", error_code=None):
        return {
            "status": status, "capability": cap, "provider": self.provider,
            "error_code": error_code, "reason_codes": [],
            "correlation_id": "synthetic-test-only", "evidence": {"data": data},
        }


def exercise(port, **changes):
    args = {
        "read": port, "release_candidate_sha": CANDIDATE,
        "running_revision": BASELINE, "phase": "before",
        "created_after": START, "created_before": END,
        "page_size": 5, "now": NOW,
    }
    args.update(changes)
    return run_ticket_read_canary(**args)


def test_full_pagination_and_exact_read_produces_content_free_summary():
    port = GovernedReadFixture()
    summary = exercise(port)
    assert summary["status"] == "PASS"
    assert summary["count_verified"] == 9
    assert summary["enumerated_count"] == 9
    assert summary["pages_verified"] == 2
    assert summary["exact_ticket_read_verified"] is True
    assert summary["provider_error_count"] == 0
    assert summary["raw_customer_content_retained"] is False
    assert summary["independent_requester_authorization_required"] is True
    assert [a[0] for a in port.calls] == [
        "service.ticket.count", "service.ticket.search",
        "service.ticket.search", "service.ticket.read",
    ]
    assert port.calls[1][1]["page_size"] == 5
    assert port.calls[2][1]["after_resource_id"] == 105
    assert port.calls[3][1] == {"resource_id": 101}
    assert all("created_after" in a[1] and "created_before" in a[1]
               for a in port.calls[:3])
    encoded = json.dumps(summary, sort_keys=True)
    assert "SECRET-CUSTOMER-DATA" not in encoded
    assert "private@example.invalid" not in encoded
    assert "101" not in encoded


def test_post_deploy_requires_actual_running_sha_equal_to_candidate():
    port = GovernedReadFixture()
    with pytest.raises(TicketReadCanaryError, match="post_release_revision_mismatch"):
        exercise(port, phase="after")
    assert port.calls == []
    summary = exercise(port, phase="after", running_revision=CANDIDATE)
    assert summary["phase"] == "after"
    assert summary["running_revision"] == CANDIDATE


@pytest.mark.parametrize("capability", [
    "service.ticket.count", "service.ticket.search", "service.ticket.read",
])
def test_any_denied_read_fails_closed(capability):
    port = GovernedReadFixture(failed_capability=capability)
    with pytest.raises(TicketReadCanaryError, match="governed_read_not_successful"):
        exercise(port)


def test_wrong_provider_fails_closed():
    with pytest.raises(TicketReadCanaryError, match="governed_read_not_successful"):
        exercise(GovernedReadFixture(response_provider="unknown"))


@pytest.mark.parametrize("count,ids,expected", [
    (10, list(range(101, 110)), "ticket_list_empty_or_malformed"),
    (0, [], "count_missing_or_empty"),
    (9, list(range(101, 109)) + [108], "duplicate_ticket_on_page"),
    (3, list(range(101, 110)), "search_exceeds_count"),
    (999, list(range(101, 110)), "sample_exceeds_page_budget"),
])
def test_count_and_complete_pagination_are_mandatory(count, ids, expected):
    with pytest.raises(TicketReadCanaryError, match=expected):
        exercise(GovernedReadFixture(count=count, ids=ids))


def test_exact_read_must_match_enumerated_id():
    with pytest.raises(TicketReadCanaryError, match="exact_ticket_read_mismatch"):
        exercise(GovernedReadFixture(read_id=987654))


@pytest.mark.parametrize("bad", [
    {"release_candidate_sha": "bad"},
    {"running_revision": "not-a-sha"},
    {"phase": "other"},
    {"page_size": 0},
    {"page_size": 101},
    {"max_pages": 0},
    {"max_pages": 51},
    {"created_after": "2026-10-27T13:00:00Z",
     "created_before": "2026-10-27T11:30:00Z"},
    {"created_after": "2026-10-19T00:00:00Z"},
    {"created_before": "2026-10-28T00:00:00Z"},
    {"created_before": "no-date"},
    {"created_after": "2026-10-27T00:00:00"},
])
def test_invalid_input_denied_before_access(bad):
    port = GovernedReadFixture()
    with pytest.raises(TicketReadCanaryError):
        exercise(port, **bad)
    assert port.calls == []


def test_provider_exception_never_discloses_sensitive_error():
    def denied(capability, arguments):
        raise RuntimeError("SECRET-PROVIDER-TOKEN person@example.invalid")

    with pytest.raises(TicketReadCanaryError) as exc:
        exercise(denied)
    assert str(exc.value) == "governed_read_exception"
    assert exc.value.__cause__ is None


def test_no_raw_read_evidence_is_never_accepted():
    with pytest.raises(TicketReadCanaryError, match="read_evidence_missing"):
        exercise(lambda cap, args: {
            "status": "succeeded", "provider": "autotask", "error_code": None,
        })

from __future__ import annotations

from types import SimpleNamespace
import pytest

from jason_runtime.autotask_client_notification import (
    AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
    AutotaskClientNotificationConnector,
)
from jason_runtime.client_outbound_opt_in import (
    CLIENT_OUTBOUND_OPT_IN_FIELD,
    JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE,
    JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV,
    ClientOutboundOptInDenied,
    company_opt_in_gate_enabled,
    company_outbound_opted_in,
)


def _company(value="True", company_id=827):
    return {
        "id": company_id,
        "userDefinedFields": [
            {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": value}
        ],
    }


@pytest.mark.parametrize("value", ["True", " TRUE ", True])
def test_exact_true_opt_in(value):
    assert company_outbound_opted_in(_company(value), expected_id=827)


@pytest.mark.parametrize("value", ["False", "", None, False, "Yes", "1", 1])
def test_only_explicit_true_counts(value):
    assert not company_outbound_opted_in(_company(value), expected_id=827)


def test_missing_duplicate_and_cross_company_fail_closed():
    assert not company_outbound_opted_in({"id": 827}, expected_id=827)
    assert not company_outbound_opted_in(_company(), expected_id=828)
    duplicate = _company()
    duplicate["userDefinedFields"].append(
        {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "True"}
    )
    assert not company_outbound_opted_in(duplicate, expected_id=827)
    assert not company_outbound_opted_in(
        {"id": 827, "userDefinedFields": [{ "name": "other", "value": "True"}]},
        expected_id=827,
    )


def test_profile_off_by_default_and_unknown_profile_denied(monkeypatch):
    monkeypatch.delenv(JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV, raising=False)
    assert company_opt_in_gate_enabled() is False
    monkeypatch.setenv(JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV, "unknown")
    with pytest.raises(ClientOutboundOptInDenied, match="PROFILE_INVALID"):
        company_opt_in_gate_enabled()


@pytest.mark.parametrize("opt_value", ["True", "False", None])
def test_connector_company_gate_precedes_contact_and_send(monkeypatch, opt_value):
    monkeypatch.setenv(
        JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV,
        JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE,
    )
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    )
    calls = []

    class FakeReads:
        def _read_item(self, *, request, capability, arguments):
            calls.append(capability)
            if capability == "autotask.ticket.get":
                return {"id": 7751, "companyID": 827, "contactID": 123,
                        "ticketNumber": "T20260001.0001"}
            if capability == "autotask.company.get":
                return _company(opt_value)
            if capability == "autotask.contact.get":
                return {"companyID": 827, "emailAddress": "client@example.com",
                        "receivesEmailNotifications": True}
            raise AssertionError(f"unexpected provider request: {capability}")

    # Unapproved template is always rejected even if the Company opted in.
    request = SimpleNamespace(arguments={
        "workflow_id": "not-approved",
        "template_id": "not-approved",
        "payload": {"ticketID": 7751, "title": "Unknown",
                    "description": "Unapproved message"},
    })
    if opt_value == "True":
        with pytest.raises(Exception, match="WORKFLOW_TEMPLATE_NOT_APPROVED"):
            AutotaskClientNotificationConnector._validate_scope(
                FakeReads(), request, 7751
            )
        assert calls == ["autotask.ticket.get", "autotask.company.get",
                         "autotask.contact.get"]
    else:
        with pytest.raises(ClientOutboundOptInDenied, match="COMPANY_NOT_OPTED_IN"):
            AutotaskClientNotificationConnector._validate_scope(
                FakeReads(), request, 7751
            )
        assert calls == ["autotask.ticket.get", "autotask.company.get"]

def test_xyz_company_test_approval_is_not_company_udf_enablement():
    """The owner's test-recipient consent is not a skip of Company opt-in."""
    assert not company_outbound_opted_in(
        {"id": 1158, "userDefinedFields": []}, expected_id=1158,
    )
    assert not company_outbound_opted_in(
        {"id": 1158, "userDefinedFields": [
            {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "False"},
        ]}, expected_id=1158,
    )
    assert company_outbound_opted_in(
        {"id": 1158, "userDefinedFields": [
            {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "True"},
        ]}, expected_id=1158,
    )
    assert not company_outbound_opted_in(
        {"id": 1158, "userDefinedFields": [
            {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "True"},
        ]}, expected_id=597,
    )

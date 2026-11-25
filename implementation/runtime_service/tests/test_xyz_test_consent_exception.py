"""Reusable XYZ Test Company consent exception, without a new sender.

Any authentic XYZ-owned ticket and any source-approved template may be used;
only the designated Gmail contact may receive the client-visible note.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from jason_runtime.approved_client_messages import resolve_approved_client_message
from jason_runtime.autotask_client_notification import (
    AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
    XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
    XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
    AutotaskClientNotificationConnector,
    AutotaskClientNotificationScopeError,
)
from jason_runtime.client_outbound_opt_in import (
    CLIENT_OUTBOUND_OPT_IN_FIELD,
    JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE,
    JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV,
    JASON_XYZ_TEST_CONSENT_PROFILE,
    JASON_XYZ_TEST_CONSENT_PROFILE_ENV,
    ClientOutboundOptInDenied,
)


def _activate(monkeypatch, *, test=True, udf=True):
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    )
    if udf:
        monkeypatch.setenv(
            JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV,
            JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE,
        )
    else:
        monkeypatch.delenv(JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE_ENV, raising=False)
    if test:
        monkeypatch.setenv(
            JASON_XYZ_TEST_CONSENT_PROFILE_ENV, JASON_XYZ_TEST_CONSENT_PROFILE,
        )
    else:
        monkeypatch.delenv(JASON_XYZ_TEST_CONSENT_PROFILE_ENV, raising=False)


def _scenario(
    *, ticket_id=141431, ticket_number="T20260926.0088",
    workflow=XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
    template=XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
    ticket_changes=None, company_changes=None, contact_changes=None,
    company_udfs=None, recipient="al.bccomputers@gmail.com",
):
    ticket = {
        "id": ticket_id, "ticketNumber": ticket_number,
        "companyID": 1158, "contactID": 30683022,
    }
    company = {
        "id": 1158, "companyName": "XYZ Test Company",
        "userDefinedFields": [
            {"name": "OtherField", "value": "Preserved"},
        ] if company_udfs is None else company_udfs,
    }
    contact = {
        "id": 30683022, "companyID": 1158,
        "emailAddress": "al.bccomputers@gmail.com",
        "receivesEmailNotifications": True,
    }
    ticket.update(ticket_changes or {})
    company.update(company_changes or {})
    contact.update(contact_changes or {})
    approved = resolve_approved_client_message(
        workflow_id=workflow,
        template_id=template,
    )
    req = SimpleNamespace(arguments={
        "workflow_id": workflow, "template_id": template,
        "recipient": recipient,
        "payload": {
            "ticketID": ticket_id, "title": approved.title,
            "description": approved.body,
        },
    })
    reads = []

    class Provider:
        def _read_item(self, *, request, capability, arguments):
            reads.append(capability)
            if capability == "autotask.ticket.get":
                return deepcopy(ticket)
            if capability == "autotask.company.get":
                return deepcopy(company)
            if capability == "autotask.contact.get":
                return deepcopy(contact)
            raise AssertionError("unexpected provider request")

    return Provider(), req, reads


@pytest.mark.parametrize(
    "ticket_id,ticket_number,workflow,template",
    [
        (141431, "T20260926.0088",
         XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
         XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE),
        (7701, "T20240821.0001",
         XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
         XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE),
        (141431, "T20260926.0088",
         "vulscan_missing_patch", "vulscan-approved-or-installed-v1"),
        (7701, "T20240821.0001",
         "vulscan_missing_patch", "vulscan-approved-or-installed-v1"),
    ],
)
def test_any_verified_xyz_ticket_and_approved_template_pass(
    monkeypatch, ticket_id, ticket_number, workflow, template
):
    _activate(monkeypatch)
    provider, req, reads = _scenario(
        ticket_id=ticket_id, ticket_number=ticket_number,
        workflow=workflow, template=template,
    )
    assert AutotaskClientNotificationConnector._validate_scope(
        provider, req, ticket_id
    ) is None
    assert reads == [
        "autotask.ticket.get", "autotask.company.get",
        "autotask.contact.get",
    ]


@pytest.mark.parametrize("udfs", [
    [{"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "False"}],
    [{"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": ""}],
    [{"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": None}],
    [{"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "True"},
     {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "False"}],
])
def test_explicit_nontrue_or_ambiguous_optin_blocks_test_exception(monkeypatch, udfs):
    _activate(monkeypatch)
    provider, req, reads = _scenario(company_udfs=udfs)
    with pytest.raises(ClientOutboundOptInDenied, match="COMPANY_NOT_OPTED_IN"):
        AutotaskClientNotificationConnector._validate_scope(
            provider, req, 141431
        )
    assert reads == ["autotask.ticket.get", "autotask.company.get"]


def test_true_udf_uses_normal_gate_and_test_inbox_still_required(monkeypatch):
    _activate(monkeypatch)
    provider, req, reads = _scenario(company_udfs=[
        {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": "True"},
    ])
    assert AutotaskClientNotificationConnector._validate_scope(
        provider, req, 141431
    ) is None
    assert "autotask.contact.get" in reads


@pytest.mark.parametrize("test,udf", [(False, True), (True, False)])
def test_missing_one_necessary_activation_gate_fails(monkeypatch, test, udf):
    _activate(monkeypatch, test=test, udf=udf)
    provider, req, reads = _scenario()
    if not test:
        with pytest.raises(ClientOutboundOptInDenied, match="COMPANY_NOT_OPTED_IN"):
            AutotaskClientNotificationConnector._validate_scope(
                provider, req, 141431
            )
    else:
        with pytest.raises(ClientOutboundOptInDenied, match="REQUIRES_UDF_GATE"):
            AutotaskClientNotificationConnector._validate_scope(
                provider, req, 141431
            )


@pytest.mark.parametrize("field,value,where", [
    ("id", 7701, "ticket"),
    ("ticketNumber", "", "ticket"),
    ("companyID", 597, "ticket"),
    ("contactID", 0, "ticket"),
    ("id", 597, "company"),
    ("companyID", 597, "contact"),
    ("emailAddress", "someoneelse@gmail.com", "contact"),
    ("receivesEmailNotifications", False, "contact"),
])
def test_cross_company_wrong_ticket_or_wrong_contact_fails_closed(
    monkeypatch, field, value, where
):
    _activate(monkeypatch)
    kwargs = {f"{where}_changes": {field: value}}
    provider, req, reads = _scenario(**kwargs)
    with pytest.raises((ClientOutboundOptInDenied, AutotaskClientNotificationScopeError)):
        AutotaskClientNotificationConnector._validate_scope(
            provider, req, 141431
        )


def test_different_requested_recipient_rejected(monkeypatch):
    _activate(monkeypatch)
    provider, req, reads = _scenario(recipient="other@example.com")
    with pytest.raises(AutotaskClientNotificationScopeError, match="SANDBOX_SCOPE_REQUIRED"):
        AutotaskClientNotificationConnector._validate_scope(provider, req, 141431)


def test_unknown_template_not_authorized_even_for_xyz(monkeypatch):
    _activate(monkeypatch)
    provider, req, reads = _scenario()
    req.arguments["workflow_id"] = "unapproved"
    req.arguments["template_id"] = "unapproved"
    with pytest.raises(AutotaskClientNotificationScopeError, match="WORKFLOW_TEMPLATE_NOT_APPROVED"):
        AutotaskClientNotificationConnector._validate_scope(provider, req, 141431)


def test_wrong_sandbox_profile_fails_closed(monkeypatch):
    _activate(monkeypatch)
    monkeypatch.setenv(JASON_XYZ_TEST_CONSENT_PROFILE_ENV, "all-companies")
    provider, req, _ = _scenario()
    with pytest.raises(ClientOutboundOptInDenied, match="PROFILE_INVALID"):
        AutotaskClientNotificationConnector._validate_scope(provider, req, 141431)

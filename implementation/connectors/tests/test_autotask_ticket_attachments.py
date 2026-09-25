from __future__ import annotations

import base64
from typing import Any, Mapping

import pytest

from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest


class Secrets:
    def resolve(self, logical_name, context):
        del context
        assert logical_name == "autotask.readonly"
        return {"username":"read@example.invalid","secret":"s","integration_code":"c"}


class Audit:
    def record(self, *args, **kwargs): pass


class Transport:
    def __init__(self, company_id=333):
        self.company_id=company_id
        self.requests=[]
        self.data=base64.b64encode(b"ticket evidence").decode()
    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
        self.requests.append((method,url,params,json))
        if url.endswith("/v1.0/zoneInformation"):
            return {"url":"https://webservices3.autotask.net/atservicesrest/"}
        if url.endswith("/V1.0/Tickets/query"):
            return {"items":[{"id":140000,"companyID":self.company_id}],"pageDetails":{"count":1,"requestCount":2}}
        if url.endswith("/V1.0/Tickets/140000/Attachments"):
            return {"items":[{"id":9,"ticketID":140000,"fullPath":"evidence.txt","data":self.data}]}
        if url.endswith("/V1.0/Tickets/140000/Attachments/9"):
            return {"items":[{"id":9,"ticketID":140000,"fullPath":"evidence.txt","data":self.data}]}
        raise AssertionError(f"unexpected {method} {url}")


def req(capability, *, max_bytes=None):
    args={"company_id":333,"ticket_id":140000}
    if capability != "autotask.ticket.attachments.list": args["attachment_id"]=9
    if max_bytes is not None: args["max_bytes"]=max_bytes
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr",principal_id="person-al",organization_id="aot",
            client_id="333",capability=capability,mode="observe",
        ),
        arguments=args,
    )


def connector(transport):
    return AutotaskImpersonatingConnector(
        secrets=Secrets(),transport=transport,audit=Audit(),bindings=None
    )


def test_metadata_list_strips_file_content():
    t=Transport(); result=connector(t).execute(req("autotask.ticket.attachments.list"))
    assert result.data["items"][0]["id"] == 9
    assert "data" not in result.data["items"][0]


def test_content_read_returns_bounded_base64_only_after_scope_check():
    t=Transport(); result=connector(t).execute(req("autotask.ticket.attachment.content.get",max_bytes=100))
    assert result.data["items"][0]["data"] == t.data


def test_cross_company_ticket_fails_before_attachment_endpoint():
    t=Transport(company_id=311)
    with pytest.raises(PermissionError, match="TICKET_COMPANY_MISMATCH"):
        connector(t).execute(req("autotask.ticket.attachments.list"))
    assert not any(url.endswith("/Attachments") for _,url,_,_ in t.requests)

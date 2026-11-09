"""V5 Teams sender only notifies the normal account, never approves."""
from dataclasses import replace
from tempfile import TemporaryDirectory
from pathlib import Path
from jason_runtime.mobile_release_approval import read_mobile_release_policy
from implementation.runtime_service.tests.test_release_v5_aot_policy import new_policy
from types import SimpleNamespace
from uuid import UUID

import pytest

from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from implementation.runtime_service.tests.v5_synthetic_identity import (
    AOT_TENANT, AOT_REQUESTER_OID, AOT_ADMIN_OID, NOTICE_URL, CHANNEL,
)
from jason_runtime.teams_communication_service import TeamsDeliveryReceipt
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest, ApprovalRequestStatus,
)
from datetime import datetime, timedelta, timezone


NOW=datetime.now(timezone.utc).replace(microsecond=0)
REGULAR_JASON="person-entra-"+UUID(AOT_REQUESTER_OID).hex


def _request():
    return ApprovalRequest(
        approval_id="relapproval-" + "a"*32,
        request_id="mobile-release:release-"+"b"*16,
        correlation_id="mobile-release:"+"b"*40,
        organization_id="aot", client_id=None,
        requested_by="svc-jason-release-manager",
        capability="release.production.approve",
        requested_mode="release:"+"b"*40,
        requested_at=NOW, expires_at=NOW+timedelta(minutes=10),
        authorized_approver_ids=("person-al",),
        metadata={
            "approval_channel":CHANNEL,
            "notice_to_entra_oid":AOT_REQUESTER_OID,
            "admin_approver_entra_oid":AOT_ADMIN_OID,
            "scope_sha256":"c"*64,
        },
    )


def _bind(oid=AOT_REQUESTER_OID):
    return SimpleNamespace(
        status="active", microsoft_tenant_id=AOT_TENANT,
        microsoft_object_id=oid,
        jason_identity_id="person-entra-"+UUID(oid).hex,
        client_id=None,
    )


def _sender(binding):
    seen=[]
    class BindingReader:
        def find(self, **kwargs):
            seen.append(("lookup",kwargs))
            return binding
    transport=SimpleNamespace(send=lambda **kwargs:(
        seen.append(("send",kwargs)) or
        TeamsDeliveryReceipt(
            message_id="verified-synthetic-provider-id",
            conversation_id="synthetic-conversation",
            recipient_identity_id=kwargs["binding"].jason_identity_id,
        )
    ))
    sender=TeamsGatewayPlaybookApprovalSender(
        gateway_url="https://gateway.test",token_file="/nonexistent",
        bindings=BindingReader(),owner_identity_ids=("person-al",),
    )
    sender._existing_transport=lambda:transport
    return sender,seen


def _call(sender,request=None,**kwargs):
    with TemporaryDirectory(prefix="v5-synthetic-notice-") as temp:
        reviewed=read_mobile_release_policy(new_policy(Path(temp)))
        source=request or _request()
        source=replace(source,metadata={
            **source.metadata,"owner_policy_sha256":reviewed.policy_sha256,
        })
        args=dict(
            request=source,reviewed_policy=reviewed,
            tenant_id=AOT_TENANT,
            regular_oid=AOT_REQUESTER_OID,
            admin_oid=AOT_ADMIN_OID,
            notice_url=NOTICE_URL,
        )
        args.update(kwargs)
        return sender.send_v5_owner_release_notice(**args)


def test_v5_uses_existing_gateway_to_regular_only_with_no_approval_button():
    sender,seen=_sender(_bind())
    assert _call(sender)==("verified-synthetic-provider-id",)
    assert len(seen)==2
    assert seen[0][1]=={
        "microsoft_tenant_id":AOT_TENANT,
        "microsoft_object_id":AOT_REQUESTER_OID,
    }
    posted=seen[1][1]
    assert posted["card"] is None
    assert posted["binding"].microsoft_object_id==AOT_REQUESTER_OID
    assert "CANNOT authorize" in posted["text"]
    assert "request=relapproval-"+"a"*32 in posted["text"]
    assert "Action.Submit" not in posted["text"]


@pytest.mark.parametrize("change",[
    {"regular_oid":AOT_ADMIN_OID},
    {"admin_oid":AOT_REQUESTER_OID},
    {"tenant_id":"00000000-0000-0000-0000-000000000001"},
    {"notice_url":"https://attacker.example/admin/release-approval"},
    {"request":replace(_request(),authorized_approver_ids=("attacker",))},
    {"request":replace(_request(),metadata={
        "approval_channel":CHANNEL,
        "notice_to_entra_oid":AOT_ADMIN_OID,
        "admin_approver_entra_oid":AOT_ADMIN_OID,
    })},
])
def test_v5_rejects_any_changed_recipient_or_claimed_approver(change):
    sender,seen=_sender(_bind())
    with pytest.raises(PermissionError):
        _call(sender,**change)
    assert not seen


def test_v5_refuses_admin_teams_account_even_if_binding_reader_returns_it():
    sender,seen=_sender(_bind(AOT_ADMIN_OID))
    with pytest.raises(PermissionError,match="REGULAR_TEAMS_REQUESTER_BINDING"):
        _call(sender)
    assert all(label!="send" for label,_ in seen)


def test_v5_rejects_synthetic_or_inconsistent_delivery_evidence():
    from dataclasses import replace as dc_replace
    for receipt in (
        TeamsDeliveryReceipt(
            message_id="accepted:synthetic", conversation_id="fake",
            recipient_identity_id=REGULAR_JASON,
            message_id_synthetic=True,
            delivery_evidence_type="provider_call_completed_without_message_id",
            delivery_state="provider_accepted_delivery_unverified",
        ),
        TeamsDeliveryReceipt(
            message_id="accepted:synthetic", conversation_id="fake",
            recipient_identity_id=REGULAR_JASON,
        ),
        TeamsDeliveryReceipt(
            message_id="provider-id", conversation_id="fake",
            recipient_identity_id=REGULAR_JASON,
            delivery_state="provider_accepted_delivery_unverified",
        ),
    ):
        sender, seen = _sender(_bind())
        sender._existing_transport=lambda value=receipt: SimpleNamespace(
            send=lambda **kwargs: value,
        )
        with pytest.raises(PermissionError,match="V5_TEAMS_NOTICE_PROVIDER_DELIVERY_UNVERIFIED"):
            _call(sender)


def test_v5_rejects_notice_delivered_to_different_jason_identity():
    sender, seen = _sender(_bind())
    sender._existing_transport=lambda: SimpleNamespace(
        send=lambda **kwargs: TeamsDeliveryReceipt(
            message_id="provider-id", conversation_id="fake",
            recipient_identity_id="different-user",
        ),
    )
    with pytest.raises(PermissionError,match="V5_TEAMS_NOTICE_RECIPIENT_NOT_VERIFIED"):
        _call(sender)

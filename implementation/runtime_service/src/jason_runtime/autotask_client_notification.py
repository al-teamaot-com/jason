from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.core.contracts import AuditSink, ConnectorRequest, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
)
from orchestrator.service import CapabilityInvoker

from .autotask_internal_note import (
    AutotaskInternalNoteConnector,
    _internal_note_definition,
    _internal_note_provider,
)
from .vulscan_client_policy import (
    GROMELSKI_COMPANY_ID,
    GROMELSKI_PRIMARY_CONTACT_ID,
    VULSCAN_CLIENT_NOTE_BODY,
    VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    VULSCAN_CLIENT_NOTE_TITLE,
)

AUTOTASK_CLIENT_NOTIFICATION_PROVIDER = "autotask_client_notification"
AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV = "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE"

AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE = "xyz-test-company-client-notification-v1"
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID = 1158
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_NAME = "XYZ Test Company"

AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE = (
    "gromelski-vulscan-client-notification-v1"
)
AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_EMAIL = "chris.benton@e-gai.com"

_SUPPORTED_PROFILES = frozenset(
    {
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
        AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE,
    }
)

_PROVIDER_CAPABILITY_MAP = {
    (
        AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
    ): "autotask.ticket.note.create",
}


class AutotaskClientNotificationScopeError(PermissionError):
    """Fail-closed client-notification scope violation."""


@dataclass(frozen=True, slots=True)
class ClientNotificationTestScope:
    ticket_company_id: int
    contact_company_id: int
    contact_email: str


@dataclass(frozen=True, slots=True)
class AutotaskClientNotificationActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _active_profile() -> str:
    return (
        os.getenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV, "")
        .strip()
        .casefold()
    )


def client_notification_test_mode_enabled() -> bool:
    return _active_profile() == AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE


def gromelski_vulscan_notification_mode_enabled() -> bool:
    return (
        _active_profile()
        == AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE
    )


def validate_client_notification_test_scope(
    *,
    ticket_company_id: int,
    contact_company_id: int,
    contact_email: str,
    requested_recipient: str | None = None,
) -> ClientNotificationTestScope:
    if not client_notification_test_mode_enabled():
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_TEST_MODE_NOT_ENABLED"
        )
    try:
        ticket_company = int(ticket_company_id)
        contact_company = int(contact_company_id)
    except (TypeError, ValueError) as exc:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_COMPANY_ID_INVALID"
        ) from exc
    if ticket_company != AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_TICKET_COMPANY_NOT_XYZ_TEST"
        )
    if contact_company != AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_COMPANY_NOT_XYZ_TEST"
        )
    email = str(contact_email or "").strip().casefold()
    if not email or not email.endswith("@gmail.com"):
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_XYZ_GMAIL_CONTACT_REQUIRED"
        )
    requested = str(requested_recipient or "").strip().casefold()
    if requested and requested != email:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_RECIPIENT_MUST_MATCH_CONTACT"
        )
    return ClientNotificationTestScope(
        ticket_company_id=ticket_company,
        contact_company_id=contact_company,
        contact_email=email,
    )


def validate_gromelski_vulscan_scope(
    *,
    ticket_company_id: int,
    contact_id: int,
    contact_company_id: int,
    contact_email: str,
    primary_contact: bool,
    receives_email_notifications: bool,
    note_title: str,
    note_body: str,
    template_id: str | None,
    requested_recipient: str | None = None,
) -> ClientNotificationTestScope:
    if not gromelski_vulscan_notification_mode_enabled():
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_MODE_NOT_ENABLED"
        )

    try:
        ticket_company = int(ticket_company_id)
        resolved_contact_id = int(contact_id)
        contact_company = int(contact_company_id)
    except (TypeError, ValueError) as exc:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_COMPANY_OR_CONTACT_ID_INVALID"
        ) from exc

    if ticket_company != GROMELSKI_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_TICKET_COMPANY_NOT_GROMELSKI"
        )
    if contact_company != GROMELSKI_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_COMPANY_NOT_GROMELSKI"
        )
    if resolved_contact_id != GROMELSKI_PRIMARY_CONTACT_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_NOT_GROMELSKI_PRIMARY"
        )
    if primary_contact is not True:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_NOT_MARKED_PRIMARY"
        )
    if receives_email_notifications is not True:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_EMAIL_NOTIFICATIONS_DISABLED"
        )

    email = str(contact_email or "").strip().casefold()
    if email != AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_EMAIL:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_GROMELSKI_CONTACT_EMAIL_MISMATCH"
        )
    requested = str(requested_recipient or "").strip().casefold()
    if requested and requested != email:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_RECIPIENT_MUST_MATCH_CONTACT"
        )

    if str(template_id or "").strip() != VULSCAN_CLIENT_NOTE_TEMPLATE_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_VULSCAN_TEMPLATE_ID_MISMATCH"
        )
    if str(note_title or "") != VULSCAN_CLIENT_NOTE_TITLE:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_VULSCAN_TITLE_MISMATCH"
        )
    if str(note_body or "") != VULSCAN_CLIENT_NOTE_BODY:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_VULSCAN_BODY_MISMATCH"
        )

    return ClientNotificationTestScope(
        ticket_company_id=ticket_company,
        contact_company_id=contact_company,
        contact_email=email,
    )


class AutotaskClientNotificationConnector(AutotaskInternalNoteConnector):
    """Ticket-note transport plus authoritative fail-closed client scope."""

    def _read_item(
        self,
        *,
        request: ConnectorRequest,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        context = replace(request.context, capability=capability, mode="observe")
        read_request = ConnectorRequest(context=context, arguments=dict(arguments))
        credentials = self._secrets.resolve(self.logical_secret, context)
        prepared = AutotaskConnector.prepare_request(self, read_request, credentials)
        email = self._trusted_email(read_request)
        if email is None:
            raise AutotaskClientNotificationScopeError(
                "CLIENT_NOTIFICATION_REQUESTER_BINDING_REQUIRED"
            )
        resource_id = self._resolve_impersonation_resource_id(
            prepared=prepared,
            email=email,
        )
        headers = dict(prepared.headers)
        headers["ImpersonationResourceId"] = str(resource_id)
        credentials.clear()
        payload = self._transport.request(
            method="GET",
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(payload, Mapping):
            raise AutotaskClientNotificationScopeError(
                "CLIENT_NOTIFICATION_AUTHORITATIVE_READ_INVALID"
            )
        item = payload.get("item")
        return dict(item if isinstance(item, Mapping) else payload)

    def _validate_scope(self, request: ConnectorRequest, ticket_id: int) -> None:
        ticket = self._read_item(
            request=request,
            capability="autotask.ticket.get",
            arguments={"ticket_id": ticket_id},
        )
        contact_id = ticket.get("contactID")
        if contact_id in (None, "", 0, "0"):
            raise AutotaskClientNotificationScopeError(
                "CLIENT_NOTIFICATION_CONTACT_REQUIRED"
            )
        contact = self._read_item(
            request=request,
            capability="autotask.contact.get",
            arguments={"contact_id": int(contact_id)},
        )

        profile = _active_profile()
        if profile == AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE:
            validate_client_notification_test_scope(
                ticket_company_id=ticket.get("companyID"),
                contact_company_id=contact.get("companyID"),
                contact_email=str(contact.get("emailAddress") or ""),
                requested_recipient=request.arguments.get("recipient"),
            )
            return

        if profile == AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE:
            payload = request.arguments.get("payload")
            if not isinstance(payload, Mapping):
                raise AutotaskClientNotificationScopeError(
                    "CLIENT_NOTIFICATION_PAYLOAD_REQUIRED"
                )
            validate_gromelski_vulscan_scope(
                ticket_company_id=ticket.get("companyID"),
                contact_id=int(contact_id),
                contact_company_id=contact.get("companyID"),
                contact_email=str(contact.get("emailAddress") or ""),
                primary_contact=contact.get("primaryContact") is True,
                receives_email_notifications=(
                    contact.get("receivesEmailNotifications") is True
                ),
                note_title=str(payload.get("title") or ""),
                note_body=str(payload.get("description") or ""),
                template_id=request.arguments.get("template_id"),
                requested_recipient=request.arguments.get("recipient"),
            )
            return

        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_PROFILE_NOT_ENABLED"
        )

    def prepare_governed_execution(self, request: ConnectorRequest):
        expected = self._expected_payload(request)
        self._validate_scope(request, int(expected["ticketID"]))
        return super().prepare_governed_execution(request)


def _definition(*, now: datetime):
    base = _internal_note_definition(now=now)
    profile = _active_profile()
    metadata = dict(base.metadata)
    metadata.update(
        {
            "activation_state": "client_notification_source_only",
            "recipient_source": "authoritative_autotask_contact",
            "profile": profile or "disabled",
            "gromelski_vulscan_company_id": str(GROMELSKI_COMPANY_ID),
            "gromelski_vulscan_primary_contact_id": str(
                GROMELSKI_PRIMARY_CONTACT_ID
            ),
            "gromelski_vulscan_template_id": VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
        }
    )
    return replace(
        base,
        capability_name=SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
        display_name="Create Client Ticket Notification",
        business_purpose=(
            "Create one explicitly approved client-facing ticket communication "
            "inside an exact source-controlled client/template scope."
        ),
        metadata=metadata,
    )


def _provider(*, now: datetime):
    base = _internal_note_provider(now=now)
    profile = _active_profile()
    return replace(
        base,
        provider_id=AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        display_name="Autotask Governed Client Notification",
        capabilities=frozenset({SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE}),
        metadata={
            **dict(base.metadata),
            "activation_state": "client_notification_source_only",
            "profile": profile or "disabled",
        },
    )


def register_autotask_client_notification_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutotaskClientNotificationActivationState:
    capabilities.register(_definition(now=now))
    providers.register(_provider(now=now))
    profile = _active_profile()
    if not profile:
        return AutotaskClientNotificationActivationState("", False, (), ())
    if profile not in _SUPPORTED_PROFILES:
        raise RuntimeError("unsupported Autotask client-notification profile")
    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return AutotaskClientNotificationActivationState(
        profile,
        True,
        (AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,),
        (SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,),
    )


def build_autotask_client_notification_invoker(
    *,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: HttpTransport,
    audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = AutotaskClientNotificationConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        bindings=bindings,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_CLIENT_NOTIFICATION_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )


def register_autotask_client_notification_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE, invoker)

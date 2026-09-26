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
    AUTOTASK_INTERNAL_NOTE_PROVIDER,
    AutotaskInternalNoteConnector,
    _internal_note_definition,
    _internal_note_provider,
)

AUTOTASK_CLIENT_NOTIFICATION_PROVIDER = "autotask_client_notification"
AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV = "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE"
AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE = "xyz-test-company-client-notification-v1"
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID = 1158
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_NAME = "XYZ Test Company"

_PROVIDER_CAPABILITY_MAP = {
    (
        AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
    ): "autotask.ticket.note.create",
}
class AutotaskClientNotificationScopeError(PermissionError):
    """Fail-closed client-notification pilot scope violation."""


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


def client_notification_test_mode_enabled() -> bool:
    return (
        os.getenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV, "")
        .strip()
        .casefold()
        == AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE
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


class AutotaskClientNotificationConnector(AutotaskInternalNoteConnector):
    """Internal-note transport plus authoritative XYZ test-scope preflight."""

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
        validate_client_notification_test_scope(
            ticket_company_id=ticket.get("companyID"),
            contact_company_id=contact.get("companyID"),
            contact_email=str(contact.get("emailAddress") or ""),
            requested_recipient=request.arguments.get("recipient"),
        )
    def prepare_governed_execution(self, request: ConnectorRequest):
        expected = self._expected_payload(request)
        self._validate_scope(request, int(expected["ticketID"]))
        return super().prepare_governed_execution(request)


def _definition(*, now: datetime):
    base = _internal_note_definition(now=now)
    metadata = dict(base.metadata)
    metadata.update(
        {
            "activation_state": "xyz_client_notification_test_source_only",
            "test_mode": "true",
            "test_company_id": str(AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID),
            "recipient_source": "authoritative_autotask_contact",
        }
    )
    return replace(
        base,
        capability_name=SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
        display_name="Create Client Ticket Notification",
        business_purpose=(
            "Create one explicitly approved XYZ Test Company client update."
        ),
        metadata=metadata,
    )
def _provider(*, now: datetime):
    base = _internal_note_provider(now=now)
    return replace(
        base,
        provider_id=AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        display_name="Autotask XYZ Client Notification Test",
        capabilities=frozenset({SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE}),
        metadata={
            **dict(base.metadata),
            "activation_state": "xyz_client_notification_test_source_only",
            "test_company_id": str(AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID),
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
    profile = os.getenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return AutotaskClientNotificationActivationState("", False, (), ())
    if profile != AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE:
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

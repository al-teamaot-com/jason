"""Dormant-by-default runtime adapter for governed Constant Contact imports.

It reuses the existing provider secret, OAuth token store, canonical plan grant
ledger and Central Orchestrator execution-plan invoker. It creates no new
approval channel or bypass. Only a separately reviewed import pilot profile
may install its invocation binding.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from connectors.constant_contact.governed_import import (
    CAPABILITY, PROVIDER, GovernedConstantContactImportConnector,
)
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_ledger import SQLiteImportActivityLedger
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore
from connectors.constant_contact.oauth_store import EncryptedOAuthStore
from connectors.constant_contact.session import current_access_token
from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.invokers import CapabilityInvokerRegistry
from kernel.resolution import CapabilityResolutionResult

from .constant_contact_teams_approval import ExistingVerifiedPlanGrantAdapter


class ConstantContactBindingError(PermissionError):
    """Connection cannot be bound to the Owner-approved account."""


def read_protected_account_binding(path: Path, *, required_uid: int = 0) -> str:
    """Read the root-installed AOT account ID; never accept an untrusted env ID."""
    try:
        path = Path(path)
        if path.is_symlink():
            raise ValueError("Symlink")
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != required_uid
                or stat.S_IMODE(info.st_mode) & 0o037):
            raise ValueError("Unsafe AOT account binding file")
        values = json.loads(path.read_text(encoding="utf-8"))
        if (set(values) != {"organization_id", "encoded_account_id", "verification_basis"}
                or values["organization_id"] != "aot"
                or values["verification_basis"] != "owner_approved_oauth_readback"
                or not isinstance(values["encoded_account_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9]{8,64}", values["encoded_account_id"])):
            raise ValueError("Invalid account binding")
        return values["encoded_account_id"]
    except (OSError, ValueError, TypeError):
        raise ConstantContactBindingError("Protected Constant Contact account binding unavailable") from None


@dataclass(frozen=True, slots=True)
class RequesterBoundImportInvoker:
    """Authorization gate must run before any OAuth or provider access."""
    delegate: GovernedConnectorCapabilityInvoker
    bindings: Any
    connector: GovernedConstantContactImportConnector | None = None

    def _require(self, *, request: OrchestrationRequest,
                 resolution: CapabilityResolutionResult) -> None:
        binding = (
            self.bindings.find_active_by_jason_identity(
                jason_identity_id=request.principal_id,
            )
            if self.bindings is not None else None
        )
        if (resolution.selected_provider_id != PROVIDER
                or resolution.capability_name != CAPABILITY
                or request.capability_name != CAPABILITY
                or request.organization_id.strip().casefold() != "aot"
                or request.client_id is not None
                or not request.authority_allowed
                or not request.authority_context_id
                or not request.approval_present
                or not request.approval_id
                or request.requester_kind != "human"
                or request.permission_mode != "execute"
                or request.orchestration_mode is not OrchestrationMode.EXECUTE
                or binding is None):
            raise PermissionError("Governed Constant Contact import requester is not authorized")

    def invoke(self, *, request: OrchestrationRequest,
               resolution: CapabilityResolutionResult):
        raise PermissionError("Constant Contact import requires canonical prepared execution")

    def prepare_execution_plan(self, *, request: OrchestrationRequest,
                               resolution: CapabilityResolutionResult):
        self._require(request=request, resolution=resolution)
        return self.delegate.prepare_execution_plan(
            request=request, resolution=resolution,
        )

    def invoke_execution_plan(self, *, request: OrchestrationRequest,
                              resolution: CapabilityResolutionResult,
                              prepared):
        self._require(request=request, resolution=resolution)
        return self.delegate.invoke_execution_plan(
            request=request, resolution=resolution, prepared=prepared,
        )


def build_import_invoker(
    *, openbao_url: str, role_id_path: Path, secret_id_path: Path,
    oauth_db: Path, work_db: Path, claims_db: Path,
    account_binding_path: Path, transport: HttpTransport,
    bindings: Any, universal_handler: Callable[[], Any],
) -> RequesterBoundImportInvoker:
    resolver = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path, secret_id_path=secret_id_path,
    )
    context = ConnectorContext(
        correlation_id="constant-contact-governed-import",
        principal_id="svc-jason-constant-contact",
        organization_id="aot", client_id=None,
        capability=CAPABILITY, mode="execute",
    )
    # If pilot activation is explicitly enabled, require the protected token
    # and encrypted work keys at startup; never make a degraded write-capable
    # runtime appear active with missing account identity or credentials.
    account_id = read_protected_account_binding(account_binding_path)
    credentials = resolver.resolve("constant_contact.oauth_client", context)
    try:
        token_key = base64.b64decode(credentials["token_key_b64"], validate=True)
        if len(token_key) != 32:
            raise ValueError("Bad OAuth storage key")
    except (ValueError, KeyError):
        raise ConstantContactBindingError("Protected OAuth encryption key unavailable") from None
    work_key = HKDF(
        algorithm=SHA256(), length=32, salt=None,
        info=b"project-jason:constant-contact:import-work:v1",
    ).derive(token_key)
    oauth_store = EncryptedOAuthStore(oauth_db, token_key)
    work_store = EncryptedImportWorkStore(work_db, work_key)
    claims = SQLiteImportActivityLedger(claims_db)

    def session() -> tuple[str, str]:
        # Refresh serialized token through the trusted OpenBao credential path.
        current = resolver.resolve("constant_contact.oauth_client", context)
        access = current_access_token(oauth_store, current)
        account = read_protected_account_binding(account_binding_path)
        if account != account_id:
            raise ConstantContactBindingError("Approved account changed during session")
        return access, account

    def approval_factory(work):
        handler = universal_handler()
        if handler is None or not work.approval_id:
            raise ImportAuthorizationError("Canonical approved plan service is unavailable")
        return ExistingVerifiedPlanGrantAdapter(
            ledger=handler.service.ledger,
            proposals=handler.proposals,
            requests=handler.requests,
            server_owned_approval_id=work.approval_id,
            server_owned_work_id=work.work_id,
        )

    connector = GovernedConstantContactImportConnector(
        transport=transport, session=session, work_store=work_store,
        claims=claims, approvals=approval_factory,
        execute_enabled=True,
    )
    delegate = GovernedConnectorCapabilityInvoker(
        connectors={PROVIDER: connector},
        provider_capability_map={(PROVIDER, CAPABILITY): CAPABILITY},
    )
    return RequesterBoundImportInvoker(delegate=delegate, bindings=bindings, connector=connector)


def register_import_invoker(*, invokers: CapabilityInvokerRegistry,
                            invoker: RequesterBoundImportInvoker) -> None:
    invokers.register(CAPABILITY, invoker)

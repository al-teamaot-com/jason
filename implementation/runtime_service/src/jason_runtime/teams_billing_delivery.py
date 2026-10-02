"""Teams delivery adapter for procurement billing-audit notifications.

The billing reconciliation process owns billing decisions. This adapter owns
Microsoft identity binding and Teams delivery only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .teams_gateway_transport import TeamsGatewayTransport


LORI_EMAIL = "lori@teamaot.com"


class TeamsGatewayBillingAuditSender:
    def __init__(
        self,
        *,
        gateway_url: str,
        token_file: str | Path,
        bindings: Any,
        lori_email: str = LORI_EMAIL,
    ) -> None:
        self.gateway_url = str(gateway_url)
        self.token_file = Path(token_file)
        self.bindings = bindings
        self.lori_email = str(lori_email)

    def _send(
        self,
        *,
        binding: Any,
        text: str,
        card: Mapping[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "aadObjectId": str(binding.microsoft_object_id),
            "tenantId": str(binding.microsoft_tenant_id),
            "text": str(text),
        }
        if card is not None:
            payload["card"] = dict(card)
        transport = TeamsGatewayTransport(
            gateway_url=self.gateway_url,
            token_file=self.token_file,
        )
        result = transport.send(transport.prepare(payload))
        if result.get("status") != "succeeded" or not result.get("message_id"):
            raise RuntimeError("Teams hardware billing notification delivery failed")
        return str(result["message_id"])

    def identity_for_email(self, *, email_address: str) -> str | None:
        binding = self.bindings.find_active_by_email(email_address=email_address)
        if binding is None or getattr(binding, "status", None) != "active":
            return None
        identity_id = str(getattr(binding, "jason_identity_id", "") or "").strip()
        return identity_id or None

    def technician(
        self,
        *,
        jason_identity_id: str,
        text: str,
        card: Mapping[str, Any],
    ) -> str:
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=jason_identity_id
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise LookupError("technician Teams binding unavailable")
        return self._send(binding=binding, text=text, card=card)

    def lori(self, *, text: str) -> str:
        binding = self.bindings.find_active_by_email(email_address=self.lori_email)
        if binding is None or getattr(binding, "status", None) != "active":
            raise LookupError("Lori Teams binding unavailable")
        return self._send(binding=binding, text=text)

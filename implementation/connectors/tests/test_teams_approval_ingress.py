from __future__ import annotations

import unittest
from datetime import datetime, timezone

from connectors.microsoft_graph.teams_approval_ingress import (
    InMemoryMicrosoftIdentityBindings,
    InMemoryMicrosoftTenantBindings,
    TeamsApprovalIngress,
    VerifiedMicrosoftPrincipal,
)

NOW = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)


def principal(**overrides) -> VerifiedMicrosoftPrincipal:
    values = dict(
        tenant_id="tenant-a",
        object_id="object-approver",
        subject="subject-approver",
        audience="jason-teams-app",
        issuer="https://login.microsoftonline.com/tenant-a/v2.0",
        authentication_assurance="mfa",
    )
    values.update(overrides)
    return VerifiedMicrosoftPrincipal(**values)


def payload(**overrides) -> dict[str, str]:
    values = {
        "approval_id": "apr-1",
        "organization_id": "org-a",
        "decision": "approve",
        "channel_response_id": "teams-response-1",
        # Deliberately attacker-controlled-looking fields. Ingress must not use
        # these as authenticated identity.
        "approver_identity_id": "spoofed-admin",
        "tenant_id": "spoofed-tenant",
    }
    values.update(overrides)
    return values


class TeamsApprovalIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ingress = TeamsApprovalIngress(
            tenant_bindings=InMemoryMicrosoftTenantBindings({"tenant-a": "org-a"}),
            identity_bindings=InMemoryMicrosoftIdentityBindings({
                ("tenant-a", "object-approver", "org-a"): "jason-approver",
            }),
        )

    def test_authenticated_identity_overrides_untrusted_card_identity(self) -> None:
        response = self.ingress.accept_verified_interaction(
            principal=principal(), payload=payload(), decided_at=NOW,
        )
        self.assertEqual(response.approver_identity_id, "jason-approver")
        self.assertEqual(response.organization_id, "org-a")
        self.assertEqual(response.channel, "microsoft_teams")

    def test_unbound_tenant_fails_closed(self) -> None:
        with self.assertRaises(PermissionError):
            self.ingress.accept_verified_interaction(
                principal=principal(tenant_id="tenant-b"), payload=payload(), decided_at=NOW,
            )

    def test_payload_cannot_cross_authenticated_tenant_scope(self) -> None:
        with self.assertRaises(PermissionError):
            self.ingress.accept_verified_interaction(
                principal=principal(), payload=payload(organization_id="org-b"), decided_at=NOW,
            )

    def test_unbound_microsoft_object_fails_closed(self) -> None:
        with self.assertRaises(PermissionError):
            self.ingress.accept_verified_interaction(
                principal=principal(object_id="unknown-object"), payload=payload(), decided_at=NOW,
            )

    def test_principal_requires_authentication_assurance(self) -> None:
        with self.assertRaises(ValueError):
            self.ingress.accept_verified_interaction(
                principal=principal(authentication_assurance=""), payload=payload(), decided_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()

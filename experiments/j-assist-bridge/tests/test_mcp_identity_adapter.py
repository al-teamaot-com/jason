from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chatgpt_session_tool import ChatGPTSessionTool
from mcp_identity_adapter import JasonMcpTechnicianIdentity
from session_gate import Denied, SessionGate, VerifiedTechnician
from synthetic_probe import SyntheticProbe, make_probe_request


class JasonMcpIdentityAdapterTests(unittest.TestCase):
    def test_existing_microsoft_mcp_principal_is_bound_to_session(self):
        identities = [("jason-tech-a", "aot", "entra-oauth-bearer", "test-client")]
        bridge = JasonMcpTechnicianIdentity(lambda: identities[0])
        permissions = {("jason-tech-a", "12345")}
        gate = SessionGate(
            identity=lambda context: context,
            can_read_datto_device=lambda principal, device: (
                isinstance(principal, VerifiedTechnician)
                and (principal.subject, device) in permissions
            ),
            clock=lambda: 1000,
        )
        technician = bridge.current()
        receipt, token = gate.start(
            trusted_context=technician, device_uid="12345", consent=True,
        )
        synthetic = SyntheticProbe(gate).exchange(
            trusted_context=technician, session_id=receipt.session_id,
            token=token, device_uid="12345",
            request=make_probe_request("mcpbridge0001"),
        )
        tool = ChatGPTSessionTool(
            gate=gate,
            credential_lookup=lambda sid: token if sid == receipt.session_id else None,
            synthetic_receipt_lookup=lambda sid: synthetic if sid == receipt.session_id else None,
        )
        answer = bridge.read_synthetic_status(
            tool=tool, session_id=receipt.session_id, device_uid="12345"
        )
        self.assertEqual(answer["provenance"], "synthetic-test-only")
        self.assertFalse(answer["screenshot_analyzed"])
        self.assertNotIn(token, str(answer))

        # Identity changes for the same session are rejected, despite known
        # session ID and server-held credential lookup.
        identities[0] = ("jason-tech-b", "aot", "entra-oauth-bearer", "test-client")
        with self.assertRaises(Denied):
            bridge.read_synthetic_status(
                tool=tool, session_id=receipt.session_id, device_uid="12345"
            )
        identities[0] = ("jason-tech-a", "other", "entra-oauth-bearer", "test-client")
        with self.assertRaises(Denied):
            bridge.read_synthetic_status(
                tool=tool, session_id=receipt.session_id, device_uid="12345"
            )

    def test_claims_or_unverified_assurance_fail_closed(self):
        invalid = [
            None, ("aot", "tech"), ("tech", "aot", "browser-asserted", None),
            ("tech", "", "entra-oauth-bearer", None),
            ("", "aot", "entra-oauth-bearer", None),
            ("tech", "aot", "entra-oauth-bearer", ""),
            {"oid": "tech", "tid": "aot"},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(Denied):
                JasonMcpTechnicianIdentity(lambda value=value: value).current()

    def test_missing_mcp_authentication_fails_closed(self):
        with self.assertRaises(Denied):
            JasonMcpTechnicianIdentity(
                lambda: (_ for _ in ()).throw(PermissionError("no bearer"))
            ).current()


if __name__ == "__main__":
    unittest.main()

"""J-Assist Entra-group eligibility bound to the existing governed SessionGate.

The *individual* technician must pass a live server-side Microsoft Graph
membership/active-account check for the configured AOT Entra group. A separate
Datto-native device ownership check still applies. This is preproduction
composition, not production service registration or browser authorization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from entra_group_screen_authority import EntraGroupEvidence, EntraGroupScreenAuthorizer
from jassist_access_policy import JAssistEntraAccessPolicy, FileBackedJAssistPolicyReader
from entra_group_http_transport import AotGraphMembershipHttpTransport, TenantTokenProvider, HttpTransport
from entra_group_membership_reader import GraphMembershipReader
from session_gate import SessionGate, VerifiedTechnician


@dataclass(frozen=True)
class JAssistServiceBindings:
    access_policy_path: Path
    datto_account_uid: str
    # A verified Jason/Entra principal from the server authentication boundary.
    identity: Callable[[object], VerifiedTechnician]
    # Trusted canonical mapping from that individual principal to Entra oid.
    resolve_entra_user_oid: Callable[[VerifiedTechnician], str | None]
    # Server-owned Microsoft Graph user status + group-membership reader.
    read_live_membership: Callable[[str, str, str], EntraGroupEvidence | None]
    # Native Datto account/device reader; never a browser-selected account.
    datto_device_in_account: Callable[[str, str], bool]

    def build_session_gate(self) -> SessionGate:
        if (not isinstance(self.access_policy_path, Path)
                or not self.access_policy_path.is_absolute()
                or not isinstance(self.datto_account_uid, str)
                or not self.datto_account_uid.strip()
                or not all(callable(x) for x in (
                    self.identity, self.resolve_entra_user_oid,
                    self.read_live_membership, self.datto_device_in_account,
                ))):
            raise ValueError("governed J-Assist identity, Graph and Datto services required")

        policy_for = FileBackedJAssistPolicyReader(
            self.access_policy_path, policy_type=JAssistEntraAccessPolicy)
        policy = policy_for()
        if policy.aot_account_uid != self.datto_account_uid:
            raise ValueError("J-Assist policy and verified AOT Datto account mismatch")

        def can_assist(technician: VerifiedTechnician, device_uid: str) -> bool:
            try:
                before = policy_for()
                if (not before.enabled
                        or before.aot_account_uid != self.datto_account_uid):
                    return False
                authorizer = EntraGroupScreenAuthorizer(
                    group_id=before.entra_group_id,
                    resolve_entr_user_oid=self.resolve_entra_user_oid,
                    read_live_membership=self.read_live_membership,
                    device_in_aot_account=lambda uid:
                        self.datto_device_in_account(self.datto_account_uid, uid),
                )
                authorized = authorizer.can_access(
                    technician, device_uid, surface="screen_assistance")
                # A settings change during the Graph/Datto read must not
                # authenticate against an obsolete group revision.
                after = policy_for()
                return authorized is True and asdict(before) == asdict(after)
            except Exception:
                return False

        return SessionGate(
            identity=self.identity, can_read_datto_device=can_assist)


def prepare_live_bindings(*, settings_path: Path | None,
                          datto_account_uid: str | None,
                          identity: Callable | None,
                          resolve_entra_user_oid: Callable | None,
                          read_live_membership: Callable | None,
                          datto_device_in_account: Callable | None) -> SessionGate:
    """Fails closed until trusted production dependencies are injected."""
    return JAssistServiceBindings(
        settings_path, datto_account_uid, identity,
        resolve_entra_user_oid, read_live_membership,
        datto_device_in_account,
    ).build_session_gate()


def prepare_graph_backed_bindings(*, settings_path: Path,
                                  datto_account_uid: str,
                                  identity: Callable,
                                  resolve_entra_user_oid: Callable,
                                  datto_device_in_account: Callable,
                                  graph_tokens: TenantTokenProvider,
                                  graph_http: HttpTransport) -> SessionGate:
    """Use Jason's existing server-owned Graph credentials and HTTP transport.

    Reads current governed policy on each authorization AND immediately
    before each Graph group query. The browser cannot choose the group.
    No API key or new tenant credential is created here.
    """
    policy_for = FileBackedJAssistPolicyReader(
        settings_path, policy_type=JAssistEntraAccessPolicy)

    def current_group_id() -> str:
        policy = policy_for()
        if not policy.enabled or policy.aot_account_uid != datto_account_uid:
            raise PermissionError("J-Assist group eligibility is disabled")
        return policy.entra_group_id

    http = AotGraphMembershipHttpTransport(
        tokens=graph_tokens, transport=graph_http,
        approved_group_id_for=current_group_id)
    reader = GraphMembershipReader(
        get_json=http.get_json, post_json=http.post_json)
    return prepare_live_bindings(
        settings_path=settings_path,
        datto_account_uid=datto_account_uid,
        identity=identity,
        resolve_entra_user_oid=resolve_entra_user_oid,
        read_live_membership=reader,
        datto_device_in_account=datto_device_in_account,
    )

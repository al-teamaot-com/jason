"""Complete, explicit composition of J-Assist pilot service dependencies.

Constructed only from separately verified Jason runtime services. No
environment-variable switch, hard-coded secret, provider bypass, or
production route auto-registration exists. The caller injects the
already-governed Graph token/transport, native Datto capability reader,
individual AOT subject binding, and independent Owner/review attestations.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from .governed_aes_keys import GovernedJAssistKeyBroker
from .pinned_entra_jwks import PinnedAotEntraJwks
from .reviewed_frame_allowlist import AttestedPilotFrameReview
from .jassist_access_policy import FileBackedJAssistPolicyReader, JAssistEntraAccessPolicy
from .runtime_wiring import JAssistRuntimeDependencies, JAssistRunningComponents
from .trusted_relay_app import TrustedCaddyJAssistIngress
from .device_identifiers import valid_device_uid


@dataclass(frozen=True)
class PilotExactActionAttestation:
    candidate_sha: str
    reviewed_scope_sha256: str
    relay_readback_sha256: str
    aot_test_device_uid: str
    owner_approval_reference: str
    production_deployment_authorized: bool = False

    def validate(self) -> None:
        if (not all(isinstance(v,str) and re.fullmatch(r"[0-9a-f]{40}",v)
                    for v in (self.candidate_sha,))
                or not all(isinstance(v,str) and re.fullmatch(r"[0-9a-f]{64}",v)
                           for v in (self.reviewed_scope_sha256,
                                     self.relay_readback_sha256))
                or not valid_device_uid(self.aot_test_device_uid)
                or not isinstance(self.owner_approval_reference,str)
                or not re.fullmatch(r"[A-Za-z0-9._:-]{12,160}",
                                    self.owner_approval_reference)
                or self.production_deployment_authorized is not False):
            raise PermissionError("scoped nonproduction exact-action evidence required")


@dataclass(frozen=True)
class PreparedPilotService:
    ingress: TrustedCaddyJAssistIngress
    components: JAssistRunningComponents


@dataclass(frozen=True)
class JAssistPilotRuntimeFactory:
    # Managed, independently approved absolute paths on the Jason host.
    policy_path: Path
    review_policy_path: Path
    session_db_path: Path
    evidence_db_path: Path
    pinned_aot_site_uid: str
    approved_spa_client_id: str
    # Existing server-governed Microsoft and Datto operations.
    graph_tokens: object
    graph_transport: object
    governed_datto_device_read: Callable
    identity_for_context: Callable
    resolve_entra_user_oid: Callable
    resolve_active_aot_identity: Callable
    # Separate AppRole-bound OpenBao key source. No file/env fallback.
    encryption_keys: GovernedJAssistKeyBroker
    # Independent immutable approval/evidence verification.
    verify_exact_pilot_action: Callable[[PilotExactActionAttestation],bool]
    verify_review_manifest_sha256: Callable[[str],bool]
    secure_ingress_ready: Callable[[],bool]
    jwks: object | None = None

    def build(self, attestation: PilotExactActionAttestation) -> PreparedPilotService:
        if not isinstance(attestation,PilotExactActionAttestation):
            raise PermissionError("typed exact pilot approval required")
        attestation.validate()
        if (not callable(self.verify_exact_pilot_action)
                or self.verify_exact_pilot_action(attestation) is not True):
            raise PermissionError("independent exact-action approval is not verified")
        if (not callable(self.verify_review_manifest_sha256)
                or not callable(self.secure_ingress_ready)
                or not callable(self.governed_datto_device_read)):
            raise PermissionError("approved live J-Assist provider services unavailable")
        jwks = self.jwks if self.jwks is not None else PinnedAotEntraJwks()
        if not callable(jwks):
            raise ValueError("pinned Entra signing-key service required")
        policy = FileBackedJAssistPolicyReader(
            self.policy_path, policy_type=JAssistEntraAccessPolicy)()
        if (policy.enabled is not True
                or policy.aot_account_uid != self.pinned_aot_site_uid):
            raise PermissionError("pilot group policy disabled or site scope mismatched")
        reviewed = AttestedPilotFrameReview(
            policy_path=self.review_policy_path,
            verify_current_manifest=self.verify_review_manifest_sha256)
        # Check DLP policy attestation before creating any databases.
        if reviewed.ready() is not True or self.secure_ingress_ready() is not True:
            raise PermissionError("reviewed content or trusted HTTPS edge not available")
        keys = self.encryption_keys.load()

        def scoped_governed_device_read(uid):
            if uid != attestation.aot_test_device_uid:
                raise PermissionError("device outside approved exact pilot scope")
            return self.governed_datto_device_read(uid)

        deps = JAssistRuntimeDependencies.from_governed_aot_site(
            aot_site_uid=self.pinned_aot_site_uid,
            governed_device_read=scoped_governed_device_read,
            policy_path=self.policy_path,
            session_db_path=self.session_db_path,
            evidence_db_path=self.evidence_db_path,
            entra_spa_client_id=self.approved_spa_client_id,
            identity_for_context=self.identity_for_context,
            resolve_entra_user_oid=self.resolve_entra_user_oid,
            resolve_active_aot_identity=self.resolve_active_aot_identity,
            entra_signing_key_for=jwks,
            graph_tokens=self.graph_tokens,
            graph_transport=self.graph_transport,
            session_encryption_key=keys.session,
            evidence_encryption_key=keys.evidence,
            content_reviewer=reviewed,
            content_review_ready=reviewed.ready,
            secure_ingress_ready=self.secure_ingress_ready,
        )
        components = deps.build()
        return PreparedPilotService(
            ingress=TrustedCaddyJAssistIngress(gateway=components.gateway),
            components=components
        )

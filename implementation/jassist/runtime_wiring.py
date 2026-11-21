"""One production composition point for J-Assist isolated services.

All credentials, Graph/Datto readers, AOT identity bindings, content review
and TLS readiness are injected from *existing governed Jason services*.
No new provider credential, browser privilege or production route is created.
Importing this module is inert. To deploy, a separately reviewed MCP/ingress
registration and exact release approval remain necessary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .chatgpt_image_tool import ChatGPTImageEvidenceTool
from .entra_group_http_transport import AotGraphMembershipHttpTransport
from .entra_group_membership_reader import GraphMembershipReader
from .entra_send_authority import EntraSendAuthority
from .jassist_access_policy import JAssistEntraAccessPolicy, FileBackedJAssistPolicyReader
from .datto_device_proof import GovernedAotDattoDeviceProof
from .jassist_asgi_gateway import JAssistASGIGateway
from .jassist_encrypted_evidence import EncryptedJAssistEvidenceIntake
from .jassist_evidence_api import JAssistEvidenceApi
from .jassist_service_bindings import JAssistServiceBindings


@dataclass(frozen=True)
class JAssistRunningComponents:
    api: JAssistEvidenceApi
    gateway: JAssistASGIGateway
    mcp_image_tool: ChatGPTImageEvidenceTool
    durable_gate: object


@dataclass(frozen=True)
class JAssistRuntimeDependencies:
    policy_path: Path
    session_db_path: Path
    evidence_db_path: Path
    aot_datto_account_uid: str
    entra_spa_client_id: str
    # Existing Jason authenticated individual identity bindings.
    identity_for_context: Callable
    resolve_entra_user_oid: Callable
    resolve_active_aot_identity: Callable
    entra_signing_key_for: Callable
    # Server-owned governed Microsoft tenant application + Datto reads.
    graph_tokens: object
    graph_transport: object
    datto_device_in_account: Callable
    # Two scoped non-exportable server secrets from existing OpenBao sources.
    session_encryption_key: bytes
    evidence_encryption_key: bytes
    # External certified screen DLP, and deployment's trusted TLS readiness.
    content_reviewer: Callable
    content_review_ready: Callable
    secure_ingress_ready: Callable

    @classmethod
    def from_governed_aot_site(cls, *, aot_site_uid: str,
                               governed_device_read: Callable[[str], dict],
                               **verified_service_dependencies):
        """Bind only an already-authorized Jason endpoint.device.read.

        The AOT site must be pinned by Jason's governed configuration,
        never selected by the extension or supplied in browser JSON.
        """
        device_proof = GovernedAotDattoDeviceProof(
            aot_site_uid=aot_site_uid,
            governed_read=governed_device_read)
        return cls(
            aot_datto_account_uid=aot_site_uid,
            datto_device_in_account=device_proof,
            **verified_service_dependencies,
        )

    def build(self) -> JAssistRunningComponents:
        if self.session_encryption_key == self.evidence_encryption_key:
            raise ValueError("J-Assist must use separated at-rest encryption keys")
        if not all(callable(x) for x in (
            self.identity_for_context,self.resolve_entra_user_oid,
            self.resolve_active_aot_identity,self.entra_signing_key_for,
            self.datto_device_in_account,self.content_reviewer,
            self.content_review_ready,self.secure_ingress_ready)):
            raise ValueError("live governed Jason service dependencies required")
        policy_for=FileBackedJAssistPolicyReader(
            self.policy_path,policy_type=JAssistEntraAccessPolicy)

        def configured_group() -> str:
            policy=policy_for()
            if not policy.enabled or policy.aot_account_uid!=self.aot_datto_account_uid:
                raise PermissionError("J-Assist group configuration not enabled")
            return policy.entra_group_id

        graph=AotGraphMembershipHttpTransport(
            tokens=self.graph_tokens,transport=self.graph_transport,
            approved_group_id_for=configured_group)
        membership=GraphMembershipReader(
            get_json=graph.get_json,post_json=graph.post_json)
        bind=JAssistServiceBindings(
            access_policy_path=self.policy_path,
            datto_account_uid=self.aot_datto_account_uid,
            identity=self.identity_for_context,
            resolve_entra_user_oid=self.resolve_entra_user_oid,
            read_live_membership=membership,
            datto_device_in_account=self.datto_device_in_account)
        gate=bind.build_durable_session_gate(
            db_path=self.session_db_path,
            encryption_key=self.session_encryption_key)
        encrypted=EncryptedJAssistEvidenceIntake(
            db_path=self.evidence_db_path,
            encryption_key=self.evidence_encryption_key,
            gate=gate,review_content=self.content_reviewer)
        verifier=EntraSendAuthority(
            allowed_spa_client_id=self.entra_spa_client_id,
            signing_key_for=self.entra_signing_key_for,
            resolve_active_aot_identity=self.resolve_active_aot_identity,
            resolve_verified_entra_oid=self.resolve_entra_user_oid)
        api=JAssistEvidenceApi(
            authenticate_bearer=verifier.authenticate,
            durable_gate=gate,encrypted_intake=encrypted,
            content_review_ready=self.content_review_ready,
            secure_ingress_ready=self.secure_ingress_ready)
        mcp=ChatGPTImageEvidenceTool(
            intake=encrypted,credential_lookup=gate.credential_for)
        return JAssistRunningComponents(
            api=api,gateway=JAssistASGIGateway(api=api),
            mcp_image_tool=mcp,durable_gate=gate)

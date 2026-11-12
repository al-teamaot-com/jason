"""PMv4 exact Owner decision adapter for the existing authenticated Jason MCP.

The MCP handler supplies (a) a fresh bearer from its trusted auth middleware,
(b) a cryptographically verified Entra token decoder already used for MCP,
and (c) a separately verified Jason Owner principal. No request-supplied
identity, callback, private key or root override is accepted in production.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping
from pathlib import Path
import json
from urllib.request import Request, urlopen

from kernel.signed_owner_release import EXACT_OWNER_OAUTH_SUBJECTS
from tools.pmv4_shadow_owner_issuer import issue_shadow_owner_proof
from tools.pmv4_shadow_release import PRODUCTION_ROOT, ShadowReleaseDenied

# Lightweight source-location precheck only. The privileged host controller
# independently revalidates protected-main *and all required GitHub CI* with
# its authenticated read-only verifier before any production activation.
PUBLIC_MAIN_URL = "https://api.github.com/repos/al-teamaot-com/jason/branches/main"


def public_protected_main_head(candidate_sha: str) -> bool:
    """Unauthenticated public read; never replace the host's strong CI gate."""
    if not isinstance(candidate_sha, str) or len(candidate_sha) != 40 or any(
        ch not in "0123456789abcdef" for ch in candidate_sha
    ):
        return False
    try:
        req = Request(PUBLIC_MAIN_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Project-Jason-PMv4-Owner-Issuer",
        })
        with urlopen(req, timeout=8) as response:
            data = response.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            return False
        obj = json.loads(data)
        return (
            isinstance(obj, dict) and obj.get("name") == "main"
            and obj.get("protected") is True
            and isinstance(obj.get("commit"), dict)
            and obj["commit"].get("sha") == candidate_sha
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def authorize_exact_shadow_from_mcp(
    *,
    bearer_token: str,
    verified_owner_principal: str,
    verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    candidate_sha: str,
    rollback_sha: str,
    scope_sha256: str,
    manifest_sha256: str,
    freeze_sha256: str,
    affirmative_decision: str,
) -> dict[str, Any]:
    """Request one bound proof, never a standing production permission."""
    if verified_organization != "aot" or verified_owner_principal not in EXACT_OWNER_OAUTH_SUBJECTS.values():
        raise ShadowReleaseDenied("PMV4_MCP_VERIFIED_OWNER_REQUIRED")
    if affirmative_decision != "approve_exact_pmv4_shadow_release":
        raise ShadowReleaseDenied("PMV4_MCP_EXPLICIT_EXACT_APPROVAL_REQUIRED")
    if not callable(verify_entra_bearer):
        raise ShadowReleaseDenied("PMV4_MCP_ENTRA_VERIFIER_UNAVAILABLE")
    expected = {
        "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha,
        "scope_sha256": scope_sha256,
        "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
    }

    def verified_claims(token: str) -> Mapping[str, Any]:
        if token != bearer_token:
            raise ShadowReleaseDenied("PMV4_MCP_AUTHENTICATED_TOKEN_MISMATCH")
        decoded = verify_entra_bearer(token)
        if not isinstance(decoded, Mapping):
            raise ShadowReleaseDenied("PMV4_MCP_ENTRA_VERIFICATION_DENIED")
        if EXACT_OWNER_OAUTH_SUBJECTS.get(decoded.get("oid")) != verified_owner_principal:
            raise ShadowReleaseDenied("PMV4_MCP_VERIFIED_SUBJECT_MISMATCH")
        return decoded

    def exact_consent(binding: Mapping[str, Any]) -> bool:
        return (
            all(binding.get(field) == value for field, value in expected.items())
            and binding.get("owner_principal") == verified_owner_principal
            and binding.get("service") == "jason-pmv4-shadow"
        )

    # Fixed production paths and trusted CI callback; the MCP caller cannot
    # install signer material, change a path or sign a different manifest.
    return issue_shadow_owner_proof(
        root=PRODUCTION_ROOT,
        bearer_token=bearer_token,
        jwt_verifier=verified_claims,
        exact_owner_consent=exact_consent,
        protected_main_check=public_protected_main_head,
        production=True,
    )

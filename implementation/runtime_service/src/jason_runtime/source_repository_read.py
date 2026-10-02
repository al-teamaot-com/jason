from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_deadline import bounded_execution_timeout
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode
from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationRequest
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import InvocationResult

from .autonomous_repair_deployment import (
    AUTONOMOUS_REPAIR_PROFILE,
    AUTONOMOUS_REPAIR_PROFILE_ENV,
)


SOURCE_REPOSITORY_PULL_REQUEST_SEARCH = "source.repository.pull_request.search"
SOURCE_REPOSITORY_COMMIT_READ = "source.repository.commit.read"
PROVIDER = "github_source_repository"
DEFAULT_REPOSITORY = "al-teamaot-com/jason"

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SourceRepositoryActivationError(RuntimeError):
    pass


def enabled() -> bool:
    return (
        os.getenv(AUTONOMOUS_REPAIR_PROFILE_ENV, "").strip().casefold()
        == AUTONOMOUS_REPAIR_PROFILE
    )


def _capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    operation: str,
    selector_keys: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=purpose,
        owner_service="Jason Source Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "exact authorized repository",
                "GitHub API result",
                "source repository identity",
            ),
            verification_requirements=(
                "repository equals configured authorized repository",
                "request is read-only",
                "returned commit identifiers remain exact immutable SHAs",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed without repository substitution or mutation.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Expose bounded source-control evidence through reusable governed reads "
                "instead of embedding GitHub transport inside maintenance workflows."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "A broader governed source-control interface replaces this capability.",
            ),
            authoritative_change_sources=("GitHub REST API",),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "source_repository,git_repository",
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": "repository pull request commit merge sha parent release metadata",
            "mcp_action_enabled": "false",
            "activation_state": "source_only_until_existing_repair_profile_is_enabled",
        },
    )


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PROVIDER,
        display_name="GitHub Source Repository",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {
                SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
                SOURCE_REPOSITORY_COMMIT_READ,
            }
        ),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=2,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Provide bounded read-only source repository evidence for release and "
                "repair workflows."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "GitHub is replaced or a stronger source-control provider adapter supersedes it.",
            ),
            vendor_change_sources=("GitHub REST API",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "read_only": "true",
            "configured_repository_only": "true",
        },
    )


def register_source_repository_read_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> bool:
    capabilities.register(
        _capability(
            now=now,
            name=SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
            display_name="Search Source Repository Pull Requests",
            purpose=(
                "Search bounded pull-request evidence in one authorized source repository."
            ),
            operation="search",
            selector_keys="repository,state,base,limit",
        )
    )
    capabilities.register(
        _capability(
            now=now,
            name=SOURCE_REPOSITORY_COMMIT_READ,
            display_name="Read Source Repository Commit",
            purpose="Read one exact immutable commit and its parent identifiers.",
            operation="read",
            selector_keys="repository,sha",
        )
    )
    providers.register(_provider(now))

    if not enabled():
        return False

    for name in (
        SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
        SOURCE_REPOSITORY_COMMIT_READ,
    ):
        capabilities.set_lifecycle(
            capability_name=name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return True


SOURCE_PULL_REQUEST_SEARCH_GRANT_ID = (
    "grant-jason-autonomy-worker-source-repository-pull-request-search-v1"
)
SOURCE_COMMIT_READ_GRANT_ID = (
    "grant-jason-autonomy-worker-source-repository-commit-read-v1"
)


def ensure_source_repository_read_authority(identity_authority) -> tuple[str, ...]:
    if not enabled():
        return ()

    expected_identity = IdentityRecord(
        identity_id="jason-autonomy-worker",
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    existing_identity = identity_authority.identities.get(expected_identity.identity_id)
    if existing_identity is None:
        identity_authority.identities.put(expected_identity)
    elif existing_identity != expected_identity:
        raise SourceRepositoryActivationError(
            "source repository reader identity conflicts with existing JKD-001 identity"
        )

    grants = (
        AuthorityGrant(
            grant_id=SOURCE_PULL_REQUEST_SEARCH_GRANT_ID,
            subject_id="jason-autonomy-worker",
            capability=SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.OBSERVE,
            approval_required=False,
            status="active",
        ),
        AuthorityGrant(
            grant_id=SOURCE_COMMIT_READ_GRANT_ID,
            subject_id="jason-autonomy-worker",
            capability=SOURCE_REPOSITORY_COMMIT_READ,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.OBSERVE,
            approval_required=False,
            status="active",
        ),
    )
    created: list[str] = []
    for grant in grants:
        current = identity_authority.grants.get(grant.grant_id)
        if current is None:
            identity_authority.grants.put(grant)
            created.append(grant.grant_id)
        elif current != grant:
            raise SourceRepositoryActivationError(
                f"source repository authority grant conflicts: {grant.grant_id}"
            )
    return tuple(created)


def _repository(value: Any, *, configured: str) -> str:
    candidate = str(value or "").strip()
    if not _REPOSITORY.fullmatch(candidate):
        raise ValueError("repository must be owner/name")
    if candidate.casefold() != configured.casefold():
        raise PermissionError("repository is outside the configured source boundary")
    return configured


def _sha(value: Any) -> str:
    candidate = str(value or "").strip().casefold()
    if not _SHA.fullmatch(candidate):
        raise ValueError("sha must be an exact 40-character lowercase git SHA")
    return candidate


@dataclass(slots=True)
class GitHubSourceRepositoryInvoker:
    repository: str = DEFAULT_REPOSITORY
    token: str = ""
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(self.repository):
            raise ValueError("configured GitHub repository must be owner/name")

    def _get(self, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-source-repository-read",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(
            f"https://api.github.com/repos/{self.repository}{path}",
            headers=headers,
        )
        with urlopen(
            request,
            timeout=bounded_execution_timeout(self.timeout_seconds),
        ) as response:
            return json.loads(response.read().decode("utf-8"))

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.selected_provider_id != PROVIDER:
            raise PermissionError("source repository read resolved to unexpected provider")
        if request.permission_mode != "observe":
            raise PermissionError("source repository capabilities are read-only")
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved source capability does not match request")

        arguments = dict(request.arguments or {})
        repository = _repository(
            arguments.get("repository"),
            configured=self.repository,
        )

        if request.capability_name == SOURCE_REPOSITORY_PULL_REQUEST_SEARCH:
            output = self._pull_request_search(repository, arguments)
        elif request.capability_name == SOURCE_REPOSITORY_COMMIT_READ:
            output = self._commit_read(repository, arguments)
        else:
            raise LookupError(
                f"unsupported source repository capability: {request.capability_name}"
            )

        return InvocationResult(
            output={
                "provider": PROVIDER,
                "provider_capability": request.capability_name,
                "data": output,
                "evidence_ids": (
                    f"github-source:{repository}:{request.capability_name}",
                ),
                "warnings": (),
            },
            attempts=1,
        )

    def _pull_request_search(
        self,
        repository: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        allowed = {"repository", "state", "base", "limit"}
        unknown = set(arguments) - allowed
        if unknown:
            raise ValueError(
                "unsupported pull-request search arguments: "
                + ", ".join(sorted(str(value) for value in unknown))
            )
        state = str(arguments.get("state") or "closed").strip().casefold()
        if state not in {"open", "closed"}:
            raise ValueError("state must be open or closed")
        base = str(arguments.get("base") or "main").strip()
        if not base or len(base) > 128:
            raise ValueError("base must be a non-empty branch name")
        try:
            limit = int(arguments.get("limit") or 30)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        query = urlencode(
            {
                "state": state,
                "base": base,
                "sort": "updated",
                "direction": "desc",
                "per_page": limit,
            }
        )
        raw = self._get("/pulls?" + query)
        if not isinstance(raw, list):
            raise RuntimeError("GitHub pull-request response was not a list")

        items: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            merge_sha = str(item.get("merge_commit_sha") or "").strip().casefold()
            if merge_sha and not _SHA.fullmatch(merge_sha):
                merge_sha = ""
            items.append(
                {
                    "number": int(item["number"]) if item.get("number") is not None else None,
                    "state": str(item.get("state") or ""),
                    "merged_at": item.get("merged_at"),
                    "merge_commit_sha": merge_sha or None,
                    "body": str(item.get("body") or ""),
                    "title": str(item.get("title") or ""),
                }
            )
        return {"repository": repository, "items": items}

    def _commit_read(
        self,
        repository: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        allowed = {"repository", "sha"}
        unknown = set(arguments) - allowed
        if unknown:
            raise ValueError(
                "unsupported commit read arguments: "
                + ", ".join(sorted(str(value) for value in unknown))
            )
        sha = _sha(arguments.get("sha"))
        raw = self._get(f"/commits/{sha}")
        if not isinstance(raw, Mapping):
            raise RuntimeError("GitHub commit response was not an object")
        parents: list[str] = []
        for parent in raw.get("parents") or []:
            if not isinstance(parent, Mapping):
                continue
            candidate = str(parent.get("sha") or "").strip().casefold()
            if _SHA.fullmatch(candidate):
                parents.append(candidate)
        observed = str(raw.get("sha") or sha).strip().casefold()
        if not _SHA.fullmatch(observed):
            raise RuntimeError("GitHub commit response omitted exact SHA")
        return {
            "repository": repository,
            "item": {
                "sha": observed,
                "parents": parents,
            },
        }


def build_source_repository_read_invoker() -> GitHubSourceRepositoryInvoker:
    return GitHubSourceRepositoryInvoker(
        repository=os.getenv("JASON_GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip(),
        token=os.getenv("JASON_GITHUB_READ_TOKEN", "").strip(),
    )


def register_source_repository_read_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: GitHubSourceRepositoryInvoker,
) -> None:
    invokers.register(SOURCE_REPOSITORY_PULL_REQUEST_SEARCH, invoker)
    invokers.register(SOURCE_REPOSITORY_COMMIT_READ, invoker)

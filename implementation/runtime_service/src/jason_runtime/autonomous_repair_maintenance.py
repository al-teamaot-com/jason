from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from autonomous_remediation.autonomous_principal import (
    AutonomousPrincipal,
    AutonomousRequestFactory,
)
from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from kernel.capabilities import CapabilityRegistryService
from kernel.identity_authority import IdentityAuthorityService
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger

from .autonomous_repair_deployment import DEPLOYMENT_REPAIR_APPLY
from .source_repository_read import (
    DEFAULT_REPOSITORY,
    SOURCE_REPOSITORY_COMMIT_READ,
    SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
)


_META = re.compile(r"^\s*-\s*([^:]+?)\s*:\s*(.*?)\s*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _metadata(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (body or "").splitlines():
        match = _META.match(line)
        if match:
            result[_key(match.group(1))] = match.group(2).strip()
    return result


def _data(output: Mapping[str, Any]) -> Mapping[str, Any]:
    value = output.get("data")
    return value if isinstance(value, Mapping) else output


class GovernedSourceRepositoryReader:
    """Execute source-control reads only through Jason's governed capability path."""

    def __init__(self, *, request_factory: AutonomousRequestFactory, orchestrator) -> None:
        self.request_factory = request_factory
        self.orchestrator = orchestrator

    def execute(
        self,
        capability_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        request = self.request_factory.build_observe(
            capability_name=capability_name,
            arguments=dict(arguments),
            client_id=None,
            correlation_id=None,
            policy_id="autonomous-repair-source-read-v1",
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise RuntimeError(
                "autonomous repair source read failed: "
                + str(
                    result.error_code
                    or ",".join(result.reason_codes)
                    or result.status.value
                )
            )
        output = result.output
        if not isinstance(output, Mapping):
            raise RuntimeError("autonomous repair source read returned no structured output")
        return dict(output)


class RepositoryRepairCandidateSource:
    """Locate repair candidates using canonical source-repository read capabilities."""

    def __init__(
        self,
        *,
        reads: GovernedSourceRepositoryReader,
        repository: str = DEFAULT_REPOSITORY,
    ) -> None:
        self.reads = reads
        self.repository = repository

    def candidates(self, *, live_revision: str, limit: int = 30) -> list[dict[str, Any]]:
        pulls_output = self.reads.execute(
            SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
            {
                "repository": self.repository,
                "state": "closed",
                "base": "main",
                "limit": limit,
            },
        )
        pulls = _data(pulls_output).get("items")
        if not isinstance(pulls, list):
            raise RuntimeError("source pull-request search did not return items")

        found: list[dict[str, Any]] = []
        for pr in pulls:
            if not isinstance(pr, Mapping) or not pr.get("merged_at"):
                continue
            metadata = _metadata(str(pr.get("body") or ""))
            if metadata.get("release_class", "").casefold() != "autonomous-repair-candidate":
                continue
            merge_sha = str(pr.get("merge_commit_sha") or "").casefold()
            if not _SHA.fullmatch(merge_sha) or merge_sha == live_revision:
                continue

            commit_output = self.reads.execute(
                SOURCE_REPOSITORY_COMMIT_READ,
                {
                    "repository": self.repository,
                    "sha": merge_sha,
                },
            )
            commit = _data(commit_output).get("item")
            if not isinstance(commit, Mapping):
                continue
            parents = list(commit.get("parents") or [])
            if len(parents) < 2:
                continue
            production_parent = str(parents[0] or "").casefold()
            if production_parent != live_revision:
                continue

            support_item = metadata.get("support_item", "").strip().upper()
            verification = metadata.get("post_deploy_verification", "").strip()
            if not support_item or not verification:
                continue
            found.append(
                {
                    "candidate_sha": merge_sha,
                    "rollback_sha": live_revision,
                    "support_item": support_item,
                    "pr_number": int(pr["number"]),
                    "post_deploy_verification": verification,
                    "merged_at": str(pr["merged_at"]),
                }
            )

        found.sort(key=lambda item: item["merged_at"])
        return found


# Compatibility name while downstream tests/callers migrate. This is no longer a
# GitHub transport implementation; all provider access is behind canonical reads.
GitHubRepairCandidateSource = RepositoryRepairCandidateSource


class AutonomousRepairDeploymentMaintenance:
    """Queue one exact eligible repair merge through the governed orchestrator."""

    def __init__(
        self,
        *,
        request_factory: AutonomousRequestFactory,
        orchestrator,
        source: RepositoryRepairCandidateSource,
        interval_seconds: int = 300,
        source_revision: str | None = None,
        now=None,
    ) -> None:
        if interval_seconds < 60:
            raise ValueError("autonomous repair interval must be at least 60 seconds")
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.source = source
        self.interval_seconds = interval_seconds
        self.source_revision = source_revision
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.next_due_at: datetime | None = None

    def _live_revision(self) -> str:
        value = str(
            self.source_revision
            or os.getenv("JASON_SOURCE_REVISION")
            or ""
        ).strip().casefold()
        if not _SHA.fullmatch(value):
            raise RuntimeError("autonomous repair maintenance requires exact live source revision")
        return value

    def tick(self) -> bool:
        current = self.now()
        if self.next_due_at is not None and current < self.next_due_at:
            return False
        self.next_due_at = current + timedelta(seconds=self.interval_seconds)

        live_revision = self._live_revision()
        candidates = self.source.candidates(live_revision=live_revision)
        if not candidates:
            return False

        candidate = candidates[0]
        request = self.request_factory.build(
            capability_name=DEPLOYMENT_REPAIR_APPLY,
            arguments={
                "candidate_sha": candidate["candidate_sha"],
                "rollback_sha": candidate["rollback_sha"],
                "support_item": candidate["support_item"],
                "pr_number": candidate["pr_number"],
                "post_deploy_verification": candidate["post_deploy_verification"],
            },
            client_id=None,
            standing_policy=None,
            correlation_id=(
                f"corr_autonomous_repair_{candidate['candidate_sha'][:12]}"
            ),
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise RuntimeError(
                "autonomous repair queue request failed: "
                + (result.error_code or ",".join(result.reason_codes) or result.status.value)
            )
        return True


def build_autonomous_repair_deployment_maintenance(
    *,
    enabled: bool,
    identity_authority: IdentityAuthorityService,
    capabilities: CapabilityRegistryService,
    approvals,
    execution_ledger: SQLiteGovernedExecutionLedger,
    orchestrator,
    promotion_db: Path,
    interval_seconds: int = 300,
):
    if not enabled:
        return None

    request_factory = AutonomousRequestFactory(
        principal=AutonomousPrincipal(),
        authority=identity_authority,
        capabilities=capabilities,
        approvals=approvals,
        execution_ledger=execution_ledger,
        promotion_store=SQLitePlaybookAutonomyApprovalStore(promotion_db),
    )
    source_reads = GovernedSourceRepositoryReader(
        request_factory=request_factory,
        orchestrator=orchestrator,
    )
    source = RepositoryRepairCandidateSource(
        reads=source_reads,
        repository=os.getenv(
            "JASON_GITHUB_REPOSITORY",
            DEFAULT_REPOSITORY,
        ).strip(),
    )
    return AutonomousRepairDeploymentMaintenance(
        request_factory=request_factory,
        orchestrator=orchestrator,
        source=source,
        interval_seconds=interval_seconds,
    )

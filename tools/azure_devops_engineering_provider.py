#!/usr/bin/env python3
"""Fail-closed Azure DevOps engineering and release-evidence adapter.

Recovery-stage, read-only adapter. Does not deploy, merge, alter work items,
grant authority, or change the GitHub-primary production release path.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

ORGANIZATION = "aotva"
PROJECT = "Jason-Standby"
REPOSITORY_ID = "fb9676e8-36e0-43cd-b2d7-3728a94b6eec"
BASE = f"https://dev.azure.com/{ORGANIZATION}/{PROJECT}/_apis"
SHA = re.compile(r"^[a-f0-9]{40}$")
SUPPORTED_RELEASE_CHECKS = frozenset({
    "cap-001", "cap-003", "cap-007", "system-registry", "runtime-service",
    "documentation", "repository-hygiene", "conversation-experience",
    "teams-gateway", "governed-security-regressions",
})


class AzureEvidenceError(RuntimeError):
    """Missing or untrustworthy release evidence. Never substitute a pass."""


@dataclass(frozen=True)
class BuildCheck:
    pipeline_id: int
    job_name: str

    def validate(self) -> None:
        if not isinstance(self.pipeline_id, int) or self.pipeline_id <= 0:
            raise AzureEvidenceError("Pipeline ID must be a positive integer")
        if not isinstance(self.job_name, str) or not self.job_name.strip():
            raise AzureEvidenceError("Required Azure job name is missing")


class AzureEngineeringReader:
    def __init__(self, request: Callable[[str, str, dict[str, Any] | None], dict[str, Any]]):
        """Request is deliberately injectable for no-network unit testing."""
        self._request = request

    def _get(self, suffix: str, query: Mapping[str, str] | None = None) -> dict[str, Any]:
        if not suffix.startswith("/") or "://" in suffix or ".." in suffix:
            raise AzureEvidenceError("Non-canonical Azure endpoint")
        parameters = dict(query or {})
        parameters["api-version"] = "7.1"
        url = BASE + suffix + "?" + urllib.parse.urlencode(parameters)
        data = self._request("GET", url, None)
        if not isinstance(data, dict):
            raise AzureEvidenceError("Azure response is not a JSON object")
        return data

    def _post(self, suffix: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not suffix.startswith("/") or "://" in suffix or ".." in suffix:
            raise AzureEvidenceError("Non-canonical Azure endpoint")
        result = self._request("POST", BASE + suffix + "?api-version=7.1", payload)
        if not isinstance(result, dict):
            raise AzureEvidenceError("Azure response is not JSON")
        return result

    def main_sha(self) -> str:
        response = self._get(
            f"/git/repositories/{REPOSITORY_ID}/refs",
            {"filter": "heads/main"},
        )
        values = response.get("value")
        if not isinstance(values, list):
            raise AzureEvidenceError("Azure branch response lacks refs")
        main = [row for row in values if row.get("name") == "refs/heads/main"]
        if len(main) != 1:
            raise AzureEvidenceError("Exactly one main ref must be returned")
        sha = str(main[0].get("objectId") or "")
        if not SHA.fullmatch(sha):
            raise AzureEvidenceError("Azure main SHA is invalid")
        return sha

    def active_prs(self, max_count: int = 100) -> list[dict[str, Any]]:
        if not 1 <= max_count <= 100:
            raise AzureEvidenceError("PR result limit out of bounds")
        data = self._get(
            f"/git/repositories/{REPOSITORY_ID}/pullrequests",
            {"searchCriteria.status": "active", "$top": str(max_count)},
        )
        prs = data.get("value")
        if not isinstance(prs, list) or len(prs) > max_count:
            raise AzureEvidenceError("Unbounded or malformed PR results")
        for pr in prs:
            if pr.get("repository", {}).get("id") not in (None, REPOSITORY_ID):
                raise AzureEvidenceError("Cross-repository PR encountered")
        return prs

    def work_items(self, max_count: int = 100) -> list[int]:
        if not 1 <= max_count <= 100:
            raise AzureEvidenceError("WIQL limit out of bounds")
        query = (
            "SELECT [System.Id] FROM WorkItems "
            "WHERE [System.TeamProject] = 'Jason-Standby' "
            "AND [System.State] <> 'Removed' ORDER BY [System.Id] DESC"
        )
        data = self._post("/wit/wiql", {"query": query})
        refs = data.get("workItems")
        if not isinstance(refs, list) or len(refs) > max_count:
            raise AzureEvidenceError("Work item results missing or exceed limit")
        result = []
        for row in refs:
            value = row.get("id")
            if not isinstance(value, int) or value <= 0:
                raise AzureEvidenceError("Invalid work item ID")
            result.append(value)
        return result

    def work_item(self, work_item_id: int) -> dict[str, Any]:
        """Read one exact Azure Boards item; identity and project must match."""
        if not isinstance(work_item_id, int) or isinstance(work_item_id, bool) or not 1 <= work_item_id <= 100000000:
            raise AzureEvidenceError("Invalid Azure work item ID")
        data = self._get(f"/wit/workitems/{work_item_id}", {"$expand": "relations"})
        fields = data.get("fields")
        if data.get("id") != work_item_id or not isinstance(fields, dict):
            raise AzureEvidenceError("Azure work item identity or fields missing")
        if fields.get("System.TeamProject") != PROJECT:
            raise AzureEvidenceError("Work item outside authorized Azure project")
        if not isinstance(data.get("rev"), int) or data["rev"] <= 0:
            raise AzureEvidenceError("Work item revision missing")
        return data

    def pull_request(self, pr_id: int) -> dict[str, Any]:
        if not isinstance(pr_id, int) or not (1 <= pr_id <= 100000000):
            raise AzureEvidenceError("Invalid Azure pull request ID")
        value = self._get(f"/git/repositories/{REPOSITORY_ID}/pullrequests/{pr_id}")
        if value.get("pullRequestId") != pr_id:
            raise AzureEvidenceError("Azure PR identity does not match request")
        if value.get("repository", {}).get("id") not in (None, REPOSITORY_ID):
            raise AzureEvidenceError("Cross-repository PR is forbidden")
        return value

    def pull_request_files(self, pr_id: int, maximum: int = 1000) -> set[str]:
        """Compare latest PR iteration against common ancestor; fail on truncation."""
        if not isinstance(pr_id, int) or not 1 <= pr_id <= 100000000:
            raise AzureEvidenceError("Invalid PR ID")
        if not 1 <= maximum <= 2000:
            raise AzureEvidenceError("File count bound exceeded")
        iterations = self._get(
            f"/git/repositories/{REPOSITORY_ID}/pullrequests/{pr_id}/iterations"
        ).get("value")
        if not isinstance(iterations, list) or not iterations or len(iterations) > 200:
            raise AzureEvidenceError("PR iteration history unavailable or unbounded")
        latest = max((x.get("id") for x in iterations), default=None)
        if not isinstance(latest, int) or latest <= 0:
            raise AzureEvidenceError("PR iteration ID malformed")
        details = self._get(
            f"/git/repositories/{REPOSITORY_ID}/pullrequests/{pr_id}/iterations/{latest}/changes",
            {"$top": str(maximum), "$skip": "0"},
        )
        files = details.get("changeEntries")
        if (not isinstance(files, list) or len(files) > maximum
                or int(details.get("nextSkip") or 0) > 0):
            raise AzureEvidenceError("PR file list missing or truncated")
        paths = set()
        for item in files:
            path = item.get("item", {}).get("path")
            if not isinstance(path, str) or not path.startswith("/") or not path[1:]:
                raise AzureEvidenceError("Invalid Azure changed file path")
            paths.add(path[1:])
            old = item.get("originalPath")
            if old:
                if not isinstance(old, str) or not old.startswith("/"):
                    raise AzureEvidenceError("Invalid original path")
                paths.add(old[1:])
        return paths

    def pr_base_sha(self, pr_id: int) -> str:
        iterations = self._get(
            f"/git/repositories/{REPOSITORY_ID}/pullrequests/{pr_id}/iterations"
        ).get("value")
        if not isinstance(iterations, list) or not iterations or len(iterations) > 200:
            raise AzureEvidenceError("PR base history unavailable")
        latest = max(iterations, key=lambda x: int(x.get("id", 0)))
        sha = str((latest.get("targetRefCommit") or {}).get("commitId") or "")
        if not SHA.fullmatch(sha):
            raise AzureEvidenceError("PR base SHA unavailable")
        return sha

    def build_evidence(
        self,
        candidate_sha: str,
        check_map: Mapping[str, BuildCheck],
        required_checks: list[str],
    ) -> dict[str, Any]:
        """Require exact main SHA AND exact candidate build/job attestations.

        Never count successful builds from feature branches, older SHAs or an
        unrelated pipeline. One Azure job can attest only its mapped check.
        """
        if not SHA.fullmatch(candidate_sha):
            raise AzureEvidenceError("Invalid release SHA")
        if self.main_sha() != candidate_sha:
            raise AzureEvidenceError("Candidate does not equal Azure main; ancestry alone is insufficient")
        if not required_checks or len(set(required_checks)) != len(required_checks):
            raise AzureEvidenceError("Missing or duplicate required checks")
        if not set(required_checks).issubset(SUPPORTED_RELEASE_CHECKS):
            raise AzureEvidenceError("Unexpected required GitHub check")
        if set(required_checks) != set(check_map):
            raise AzureEvidenceError("Azure-to-GitHub check mapping incomplete")
        for entry in check_map.values():
            entry.validate()

        evidence = {}
        failed = []
        for name in required_checks:
            mapping = check_map[name]
            payload = self._get(
                "/build/builds",
                {
                    "definitions": str(mapping.pipeline_id),
                    "branchName": "refs/heads/main",
                    "queryOrder": "finishTimeDescending",
                    "$top": "50",
                },
            )
            builds = payload.get("value")
            if not isinstance(builds, list) or len(builds) > 50:
                raise AzureEvidenceError("Invalid bounded Azure build listing")
            exact = [
                item for item in builds
                if item.get("sourceVersion") == candidate_sha
                and item.get("sourceBranch") == "refs/heads/main"
                and item.get("definition", {}).get("id") == mapping.pipeline_id
            ]
            if not exact:
                failed.append(name + ":missing_matching_main_build")
                continue
            selected = max(exact, key=lambda x: int(x.get("id", 0)))
            if selected.get("status") != "completed" or selected.get("result") != "succeeded":
                failed.append(name + ":build_not_green")
                continue
            build_id = selected.get("id")
            if not isinstance(build_id, int) or build_id <= 0:
                raise AzureEvidenceError("Invalid build ID")
            timeline = self._get(f"/build/builds/{build_id}/timeline")
            records = timeline.get("records")
            if not isinstance(records, list):
                raise AzureEvidenceError("Build timeline unavailable")
            matches = [
                item for item in records
                if item.get("type") == "Job" and item.get("name") == mapping.job_name
            ]
            if len(matches) != 1 or matches[0].get("state") != "completed" or matches[0].get("result") != "succeeded":
                failed.append(name + ":required_job_not_green")
                continue
            evidence[name] = {"pipeline_id": mapping.pipeline_id, "build_id": build_id,
                              "job": mapping.job_name, "source_sha": candidate_sha}
        return {
            "passed": not failed, "required": required_checks, "failures": failed,
            "provider": "azure-devops", "source_sha": candidate_sha, "evidence": evidence,
        }


def read_only_transport(token_provider: Callable[[], str], timeout: int = 20):
    """Only documented read/query calls; no provider writes or arbitrary domains."""
    def perform(method: str, url: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not url.startswith(BASE + "/") or method not in {"GET", "POST"}:
            raise AzureEvidenceError("Unsupported Azure API request")
        if method == "POST" and not url.startswith(BASE + "/wit/wiql?"):
            raise AzureEvidenceError("Only read-only WIQL POST is permitted")
        token = token_provider()
        if not isinstance(token, str) or not token:
            raise AzureEvidenceError("Azure access token unavailable")
        data = None if method == "GET" else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.load(response)
        except Exception as exc:
            # Never print HTTP error bodies or secrets. Caller fails closed.
            raise AzureEvidenceError("Azure API request failed") from None
        if not isinstance(result, dict):
            raise AzureEvidenceError("Malformed Azure response")
        return result
    return perform

#!/usr/bin/env python3
"""Fail-closed Azure PR documentation and concurrent-change validation.

Reusable for Azure Repos branch-policy builds; safe to run as a diagnostic now.
This does not approve, merge, or deploy PRs.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from azure_devops_engineering_provider import AzureEngineeringReader, AzureEvidenceError, read_only_transport
from azure_devops_identity import azure_devops_token
from documentation_impact_gate import validate_pull_request_body, DocumentationImpactError
from change_integration_gate import sensitive, parse_acknowledged


def validate(reader: AzureEngineeringReader, pr_id: int) -> dict[str, Any]:
    pr = reader.pull_request(pr_id)
    errors: list[str] = []
    if pr.get("status") != "active":
        errors.append("PR is not active")
    if pr.get("targetRefName") != "refs/heads/main":
        errors.append("PR does not target Azure main")
    if pr.get("isDraft") is True:
        errors.append("PR is still draft; no release or merge approval")
    body = str(pr.get("description") or "")
    try:
        validate_pull_request_body(body)
    except DocumentationImpactError as exc:
        errors.append(str(exc))
    current_main = reader.main_sha()
    if reader.pr_base_sha(pr_id) != current_main:
        errors.append("PR iteration target is stale against current Azure main")
    own_files = reader.pull_request_files(pr_id)
    current_sensitive = {name for name in own_files if sensitive(name)}
    acknowledged = parse_acknowledged(body)
    if current_sensitive:
        peers = reader.active_prs()
        if len(peers) > 100:
            raise AzureEvidenceError("PR coordination list too large")
        for peer in peers:
            other_id = peer.get("pullRequestId")
            if other_id == pr_id or peer.get("targetRefName") != "refs/heads/main":
                continue
            if not isinstance(other_id, int) or other_id <= 0:
                raise AzureEvidenceError("Invalid peer PR ID")
            overlap = sorted(current_sensitive & {
                name for name in reader.pull_request_files(other_id) if sensitive(name)
            })
            if overlap and other_id not in acknowledged:
                errors.append(
                    f"Unacknowledged active implementation overlap with PR #{other_id}: "
                    + ", ".join(overlap[:8])
                )
    return {
        "provider": "azure-devops",
        "pr_id": pr_id,
        "status": "pass" if not errors else "blocked",
        "base_sha": current_main,
        "changed_file_count": len(own_files),
        "errors": errors,
        "writes_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-id", type=int, required=True)
    args = parser.parse_args()
    try:
        # Azure Pipelines uses the job-scoped OAuth token; the private
        # certificate is never copied to a hosted CI runner.
        job_token = os.environ.get("SYSTEM_ACCESSTOKEN", "").strip()
        token_provider = (lambda: job_token) if job_token else azure_devops_token
        evidence = validate(
            AzureEngineeringReader(read_only_transport(token_provider)),
            args.pr_id,
        )
    except (AzureEvidenceError, ValueError, TypeError):
        print(json.dumps({"status": "blocked", "reason": "missing_or_invalid_azure_pr_evidence"}))
        return 3
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

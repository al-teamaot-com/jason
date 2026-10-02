from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import jason_runtime.source_repository_read as module
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)


REPO = "al-teamaot-com/jason"
SHA = "a" * 40


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def request(capability, arguments, permission="observe"):
    return SimpleNamespace(
        capability_name=capability,
        arguments=arguments,
        permission_mode=permission,
    )


def resolution(capability):
    return SimpleNamespace(
        selected_provider_id=module.PROVIDER,
        capability_name=capability,
    )


def test_pull_request_search_is_bounded_to_configured_repository(monkeypatch):
    invoker = module.GitHubSourceRepositoryInvoker(repository=REPO)
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return Response(
            [
                {
                    "number": 12,
                    "state": "closed",
                    "merged_at": "2026-10-02T12:00:00Z",
                    "merge_commit_sha": SHA,
                    "body": "body",
                    "title": "repair",
                }
            ]
        )

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    result = invoker.invoke(
        request=request(
            module.SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
            {"repository": REPO, "state": "closed", "base": "main", "limit": 30},
        ),
        resolution=resolution(module.SOURCE_REPOSITORY_PULL_REQUEST_SEARCH),
    )

    assert len(calls) == 1
    assert "/repos/al-teamaot-com/jason/pulls?" in calls[0][0]
    assert result.output["data"]["items"][0]["merge_commit_sha"] == SHA


def test_repository_substitution_fails_before_provider_call(monkeypatch):
    invoker = module.GitHubSourceRepositoryInvoker(repository=REPO)
    calls = []
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(PermissionError, match="outside the configured source boundary"):
        invoker.invoke(
            request=request(
                module.SOURCE_REPOSITORY_COMMIT_READ,
                {"repository": "someone/else", "sha": SHA},
            ),
            resolution=resolution(module.SOURCE_REPOSITORY_COMMIT_READ),
        )

    assert calls == []


def test_commit_read_returns_only_exact_sha_and_parent_evidence(monkeypatch):
    invoker = module.GitHubSourceRepositoryInvoker(repository=REPO)
    parent = "b" * 40

    monkeypatch.setattr(
        module,
        "urlopen",
        lambda req, timeout: Response(
            {
                "sha": SHA,
                "parents": [{"sha": parent}, {"sha": "c" * 40}],
                "commit": {"message": "not part of normalized contract"},
            }
        ),
    )
    result = invoker.invoke(
        request=request(
            module.SOURCE_REPOSITORY_COMMIT_READ,
            {"repository": REPO, "sha": SHA},
        ),
        resolution=resolution(module.SOURCE_REPOSITORY_COMMIT_READ),
    )

    item = result.output["data"]["item"]
    assert item == {"sha": SHA, "parents": [parent, "c" * 40]}


def test_source_repository_read_rejects_execute_permission():
    invoker = module.GitHubSourceRepositoryInvoker(repository=REPO)
    with pytest.raises(PermissionError, match="read-only"):
        invoker.invoke(
            request=request(
                module.SOURCE_REPOSITORY_COMMIT_READ,
                {"repository": REPO, "sha": SHA},
                permission="execute",
            ),
            resolution=resolution(module.SOURCE_REPOSITORY_COMMIT_READ),
        )

def test_source_repository_capabilities_stay_dormant_without_repair_profile():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(module.AUTONOMOUS_REPAIR_PROFILE_ENV, None)
        active = module.register_source_repository_read_foundation(
            capabilities=capabilities,
            providers=providers,
            now=datetime.now(timezone.utc),
        )
    assert active is False
    assert (
        capabilities.get(
            capability_name=module.SOURCE_REPOSITORY_PULL_REQUEST_SEARCH,
            version="1.0",
        ).lifecycle_status.value
        == "building"
    )


def test_exact_repair_profile_activates_source_repository_reads():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    with patch.dict(
        os.environ,
        {
            module.AUTONOMOUS_REPAIR_PROFILE_ENV: module.AUTONOMOUS_REPAIR_PROFILE,
        },
    ):
        active = module.register_source_repository_read_foundation(
            capabilities=capabilities,
            providers=providers,
            now=datetime.now(timezone.utc),
        )
    assert active is True
    assert (
        capabilities.get_current(
            capability_name=module.SOURCE_REPOSITORY_PULL_REQUEST_SEARCH
        ).lifecycle_status.value
        == "active"
    )
    assert (
        capabilities.get_current(
            capability_name=module.SOURCE_REPOSITORY_COMMIT_READ
        ).lifecycle_status.value
        == "active"
    )


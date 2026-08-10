from __future__ import annotations

import pytest

from connectors.microsoft_graph.platform import (
    MicrosoftCloudRequest,
    MicrosoftRequestPolicyError,
    build_governed_request,
)
from connectors.microsoft_graph.service_catalog import (
    MICROSOFT_ENDPOINTS,
    MICROSOFT_PERMISSION_PROFILES,
    MicrosoftOperationMode,
    MicrosoftService,
    endpoint_for,
    permission_profile,
    validate_profile_for_services,
)


def test_service_catalog_covers_core_microsoft_cloud_domains() -> None:
    expected = {
        MicrosoftService.GRAPH,
        MicrosoftService.ENTRA,
        MicrosoftService.EXCHANGE,
        MicrosoftService.SHAREPOINT,
        MicrosoftService.ONEDRIVE,
        MicrosoftService.TEAMS,
        MicrosoftService.INTUNE,
        MicrosoftService.DEFENDER,
        MicrosoftService.PURVIEW,
        MicrosoftService.SERVICE_HEALTH,
        MicrosoftService.LICENSING,
    }
    assert expected <= set(MICROSOFT_ENDPOINTS)


def test_permission_profiles_are_read_only_by_default() -> None:
    assert MICROSOFT_PERMISSION_PROFILES
    for profile in MICROSOFT_PERMISSION_PROFILES.values():
        assert profile.maximum_mode is MicrosoftOperationMode.READ
        assert profile.application_permissions


def test_graph_read_request_is_built_with_v1_endpoint() -> None:
    governed = build_governed_request(
        MicrosoftCloudRequest(
            service=MicrosoftService.ENTRA,
            method="get",
            path="/users/123",
            permission_profile_name="identity-investigation-read",
            query={"$select": "id,displayName,userPrincipalName"},
        )
    )
    assert governed.method == "GET"
    assert governed.url.startswith("https://graph.microsoft.com/v1.0/users/123?")
    assert governed.provider_name == "microsoft_entra"


def test_read_profile_cannot_be_used_for_mutation() -> None:
    request = MicrosoftCloudRequest(
        service=MicrosoftService.ENTRA,
        method="PATCH",
        path="/users/123",
        permission_profile_name="identity-investigation-read",
        mode=MicrosoftOperationMode.READ,
    )
    with pytest.raises(MicrosoftRequestPolicyError, match="Read mode"):
        build_governed_request(request)


def test_bounded_automation_is_fail_closed() -> None:
    request = MicrosoftCloudRequest(
        service=MicrosoftService.GRAPH,
        method="GET",
        path="/organization",
        permission_profile_name="directory-read",
        mode=MicrosoftOperationMode.BOUNDED_AUTOMATION,
    )
    with pytest.raises(MicrosoftRequestPolicyError, match="does not support requested mode"):
        build_governed_request(request)


def test_profile_service_mismatch_is_denied() -> None:
    profile = permission_profile("device-compliance-read")
    with pytest.raises(PermissionError, match="does not authorize"):
        validate_profile_for_services(profile, {MicrosoftService.EXCHANGE})


def test_unsafe_paths_are_rejected() -> None:
    with pytest.raises(ValueError, match="unsafe segment"):
        MicrosoftCloudRequest(
            service=MicrosoftService.GRAPH,
            method="GET",
            path="/users/../organization",
            permission_profile_name="directory-read",
        )


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(LookupError, match="not registered"):
        permission_profile("does-not-exist")


def test_graph_endpoint_is_public_cloud_only() -> None:
    endpoint = endpoint_for(MicrosoftService.GRAPH)
    assert endpoint.base_url == "https://graph.microsoft.com"
    assert endpoint.default_api_version == "v1.0"

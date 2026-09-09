from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MicrosoftCloud(StrEnum):
    PUBLIC = "public"


class MicrosoftService(StrEnum):
    GRAPH = "graph"
    ENTRA = "entra"
    EXCHANGE = "exchange"
    SHAREPOINT = "sharepoint"
    TEAMS = "teams"
    LICENSING = "licensing"


class MicrosoftOperationMode(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class MicrosoftEndpointFamily:
    service: MicrosoftService
    provider_name: str
    base_url: str
    default_api_version: str | None
    supported_modes: frozenset[MicrosoftOperationMode]
    cloud: MicrosoftCloud = MicrosoftCloud.PUBLIC


@dataclass(frozen=True, slots=True)
class MicrosoftPermissionProfile:
    name: str
    description: str
    services: frozenset[MicrosoftService]
    application_permissions: tuple[str, ...]
    maximum_mode: MicrosoftOperationMode


READ_ONLY = frozenset({MicrosoftOperationMode.READ})
GOVERNED_WRITE = frozenset({MicrosoftOperationMode.READ, MicrosoftOperationMode.WRITE})
GOVERNED_ADMIN = frozenset(
    {MicrosoftOperationMode.READ, MicrosoftOperationMode.WRITE, MicrosoftOperationMode.ADMIN}
)


MICROSOFT_ENDPOINTS: dict[MicrosoftService, MicrosoftEndpointFamily] = {
    MicrosoftService.GRAPH: MicrosoftEndpointFamily(
        service=MicrosoftService.GRAPH,
        provider_name="microsoft_graph",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=READ_ONLY,
    ),
    MicrosoftService.ENTRA: MicrosoftEndpointFamily(
        service=MicrosoftService.ENTRA,
        provider_name="microsoft_entra",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_ADMIN,
    ),
    MicrosoftService.EXCHANGE: MicrosoftEndpointFamily(
        service=MicrosoftService.EXCHANGE,
        provider_name="microsoft_exchange",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
    MicrosoftService.SHAREPOINT: MicrosoftEndpointFamily(
        service=MicrosoftService.SHAREPOINT,
        provider_name="microsoft_sharepoint",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
    MicrosoftService.TEAMS: MicrosoftEndpointFamily(
        service=MicrosoftService.TEAMS,
        provider_name="microsoft_teams",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
    MicrosoftService.LICENSING: MicrosoftEndpointFamily(
        service=MicrosoftService.LICENSING,
        provider_name="microsoft_licensing",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
}


MICROSOFT_PERMISSION_PROFILES: dict[str, MicrosoftPermissionProfile] = {
    "directory-read": MicrosoftPermissionProfile(
        name="directory-read",
        description="Read-only Microsoft user profile lookup for authenticated identity enrichment.",
        services=frozenset({MicrosoftService.GRAPH}),
        application_permissions=("User.Read.All",),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "identity-investigation-read": MicrosoftPermissionProfile(
        name="identity-investigation-read",
        description="Read-only user, group, authentication, sign-in, role, and license investigation profile.",
        services=frozenset({MicrosoftService.ENTRA, MicrosoftService.LICENSING}),
        application_permissions=(
            "AuditLog.Read.All",
            "Directory.Read.All",
            "IdentityRiskEvent.Read.All",
            "IdentityRiskyUser.Read.All",
            "Reports.Read.All",
            "UserAuthenticationMethod.Read.All",
        ),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "mail-read": MicrosoftPermissionProfile(
        name="mail-read",
        description="Read-only Exchange Online mailbox and message discovery.",
        services=frozenset({MicrosoftService.EXCHANGE}),
        application_permissions=("Mail.Read",),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "mail-send": MicrosoftPermissionProfile(
        name="mail-send",
        description="Governed Exchange Online mail send profile.",
        services=frozenset({MicrosoftService.EXCHANGE}),
        application_permissions=("Mail.Send",),
        maximum_mode=MicrosoftOperationMode.WRITE,
    ),
    "sharepoint-read": MicrosoftPermissionProfile(
        name="sharepoint-read",
        description="Read-only SharePoint and OneDrive content discovery.",
        services=frozenset({MicrosoftService.SHAREPOINT}),
        application_permissions=("Sites.Read.All",),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "teams-read": MicrosoftPermissionProfile(
        name="teams-read",
        description="Read-only Teams conversation and membership discovery.",
        services=frozenset({MicrosoftService.TEAMS}),
        application_permissions=("ChannelMessage.Read.All", "Team.ReadBasic.All"),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "teams-write": MicrosoftPermissionProfile(
        name="teams-write",
        description="Governed Teams messaging and membership write profile.",
        services=frozenset({MicrosoftService.TEAMS}),
        application_permissions=("ChannelMessage.Send",),
        maximum_mode=MicrosoftOperationMode.WRITE,
    ),
    "licensing-read": MicrosoftPermissionProfile(
        name="licensing-read",
        description="Read-only Microsoft 365 license and subscription discovery.",
        services=frozenset({MicrosoftService.LICENSING}),
        application_permissions=("Organization.Read.All", "User.Read.All"),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
}


def endpoint_for(service: MicrosoftService) -> MicrosoftEndpointFamily:
    return MICROSOFT_ENDPOINTS[service]


def permission_profile(name: str) -> MicrosoftPermissionProfile:
    try:
        return MICROSOFT_PERMISSION_PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown Microsoft permission profile: {name}") from exc


def validate_profile_for_services(
    profile: MicrosoftPermissionProfile,
    services: frozenset[MicrosoftService],
) -> None:
    unsupported = services.difference(profile.services)
    if unsupported:
        names = ", ".join(sorted(service.value for service in unsupported))
        raise ValueError(
            f"Microsoft permission profile {profile.name!r} does not authorize services: {names}"
        )

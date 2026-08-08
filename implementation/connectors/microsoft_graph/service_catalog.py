from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MicrosoftCloud(Enum):
    PUBLIC = "public"


class MicrosoftService(Enum):
    GRAPH = "graph"
    ENTRA = "entra"
    EXCHANGE = "exchange_online"
    SHAREPOINT = "sharepoint_online"
    ONEDRIVE = "onedrive"
    TEAMS = "teams"
    INTUNE = "intune"
    DEFENDER = "defender"
    PURVIEW = "purview"
    SERVICE_HEALTH = "service_health"
    LICENSING = "licensing"


class MicrosoftOperationMode(Enum):
    READ = "read"
    RECOMMEND = "recommend"
    WRITE_WITH_APPROVAL = "write_with_approval"
    BOUNDED_AUTOMATION = "bounded_automation"


@dataclass(frozen=True, slots=True)
class MicrosoftEndpointFamily:
    service: MicrosoftService
    provider_name: str
    base_url: str
    default_api_version: str | None
    supported_modes: frozenset[MicrosoftOperationMode]
    notes: str = ""

    def supports(self, mode: MicrosoftOperationMode) -> bool:
        return mode in self.supported_modes


@dataclass(frozen=True, slots=True)
class MicrosoftPermissionProfile:
    name: str
    description: str
    services: frozenset[MicrosoftService]
    application_permissions: tuple[str, ...]
    maximum_mode: MicrosoftOperationMode

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Microsoft permission profile name must be non-empty.")
        if not self.services:
            raise ValueError("Microsoft permission profile must cover at least one service.")
        if any(not permission.strip() for permission in self.application_permissions):
            raise ValueError("Microsoft application permissions must be non-empty.")


READ_ONLY = frozenset({MicrosoftOperationMode.READ, MicrosoftOperationMode.RECOMMEND})
GOVERNED_WRITE = frozenset(
    {
        MicrosoftOperationMode.READ,
        MicrosoftOperationMode.RECOMMEND,
        MicrosoftOperationMode.WRITE_WITH_APPROVAL,
    }
)


MICROSOFT_ENDPOINTS: dict[MicrosoftService, MicrosoftEndpointFamily] = {
    MicrosoftService.GRAPH: MicrosoftEndpointFamily(
        service=MicrosoftService.GRAPH,
        provider_name="microsoft_graph",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
        notes="Primary API surface for Entra, users, groups, devices, Teams, SharePoint, licensing, audit, and security resources.",
    ),
    MicrosoftService.ENTRA: MicrosoftEndpointFamily(
        service=MicrosoftService.ENTRA,
        provider_name="microsoft_entra",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
        notes="Identity and directory operations are Graph-backed unless a capability explicitly requires another Microsoft endpoint.",
    ),
    MicrosoftService.EXCHANGE: MicrosoftEndpointFamily(
        service=MicrosoftService.EXCHANGE,
        provider_name="microsoft_exchange_online",
        base_url="https://outlook.office365.com",
        default_api_version=None,
        supported_modes=GOVERNED_WRITE,
        notes="Exchange Online PowerShell/REST and Graph mail surfaces are capability-selected; transport and trace features may require Exchange-specific APIs.",
    ),
    MicrosoftService.SHAREPOINT: MicrosoftEndpointFamily(
        service=MicrosoftService.SHAREPOINT,
        provider_name="microsoft_sharepoint_online",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
    MicrosoftService.ONEDRIVE: MicrosoftEndpointFamily(
        service=MicrosoftService.ONEDRIVE,
        provider_name="microsoft_onedrive",
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
    MicrosoftService.INTUNE: MicrosoftEndpointFamily(
        service=MicrosoftService.INTUNE,
        provider_name="microsoft_intune",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
    ),
    MicrosoftService.DEFENDER: MicrosoftEndpointFamily(
        service=MicrosoftService.DEFENDER,
        provider_name="microsoft_defender",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=GOVERNED_WRITE,
        notes="Security capabilities may later bind to product-specific Defender endpoints through separate governed providers.",
    ),
    MicrosoftService.PURVIEW: MicrosoftEndpointFamily(
        service=MicrosoftService.PURVIEW,
        provider_name="microsoft_purview",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=READ_ONLY,
        notes="Initial foundation is evidence and posture visibility only.",
    ),
    MicrosoftService.SERVICE_HEALTH: MicrosoftEndpointFamily(
        service=MicrosoftService.SERVICE_HEALTH,
        provider_name="microsoft_service_health",
        base_url="https://graph.microsoft.com",
        default_api_version="v1.0",
        supported_modes=READ_ONLY,
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
        description="Read-only Entra directory and organization discovery.",
        services=frozenset({MicrosoftService.GRAPH, MicrosoftService.ENTRA}),
        application_permissions=("Directory.Read.All",),
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
    "mail-investigation-read": MicrosoftPermissionProfile(
        name="mail-investigation-read",
        description="Read-only mailbox and mail-flow investigation profile; Exchange-specific permissions are governed separately.",
        services=frozenset({MicrosoftService.GRAPH, MicrosoftService.EXCHANGE}),
        application_permissions=("Mail.ReadBasic.All", "User.Read.All"),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "device-compliance-read": MicrosoftPermissionProfile(
        name="device-compliance-read",
        description="Read-only Intune managed-device and compliance investigation profile.",
        services=frozenset({MicrosoftService.INTUNE, MicrosoftService.ENTRA}),
        application_permissions=(
            "DeviceManagementManagedDevices.Read.All",
            "DeviceManagementConfiguration.Read.All",
            "Directory.Read.All",
        ),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "security-investigation-read": MicrosoftPermissionProfile(
        name="security-investigation-read",
        description="Read-only Microsoft security incident and alert investigation profile.",
        services=frozenset({MicrosoftService.DEFENDER, MicrosoftService.ENTRA}),
        application_permissions=(
            "SecurityAlert.Read.All",
            "SecurityIncident.Read.All",
            "AuditLog.Read.All",
            "Directory.Read.All",
        ),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
    "collaboration-permissions-read": MicrosoftPermissionProfile(
        name="collaboration-permissions-read",
        description="Read-only Teams, SharePoint, OneDrive, group, membership, and sharing investigation profile.",
        services=frozenset(
            {
                MicrosoftService.TEAMS,
                MicrosoftService.SHAREPOINT,
                MicrosoftService.ONEDRIVE,
            }
        ),
        application_permissions=(
            "Group.Read.All",
            "Sites.Read.All",
            "Team.ReadBasic.All",
            "Channel.ReadBasic.All",
        ),
        maximum_mode=MicrosoftOperationMode.READ,
    ),
}


def endpoint_for(service: MicrosoftService) -> MicrosoftEndpointFamily:
    try:
        return MICROSOFT_ENDPOINTS[service]
    except KeyError as exc:
        raise LookupError(f"Microsoft service is not registered: {service.value}") from exc


def permission_profile(name: str) -> MicrosoftPermissionProfile:
    normalized = name.strip().lower()
    try:
        return MICROSOFT_PERMISSION_PROFILES[normalized]
    except KeyError as exc:
        raise LookupError("Microsoft permission profile is not registered.") from exc


def validate_profile_for_services(
    profile: MicrosoftPermissionProfile,
    services: Iterable[MicrosoftService],
) -> None:
    requested = frozenset(services)
    unsupported = requested - profile.services
    if unsupported:
        names = ", ".join(sorted(service.value for service in unsupported))
        raise PermissionError(
            f"Microsoft permission profile {profile.name!r} does not authorize services: {names}."
        )

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlencode

from .service_catalog import (
    MicrosoftOperationMode,
    MicrosoftPermissionProfile,
    MicrosoftService,
    endpoint_for,
    permission_profile,
    validate_profile_for_services,
)


_ALLOWED_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_QUERY_KEYS = frozenset(
    {
        "$select",
        "$filter",
        "$top",
        "$orderby",
        "$expand",
        "$count",
        "$search",
        "$skip",
        "$skiptoken",
    }
)
_MODE_RANK = {
    MicrosoftOperationMode.READ: 0,
    MicrosoftOperationMode.WRITE: 1,
    MicrosoftOperationMode.ADMIN: 2,
}


@dataclass(frozen=True, slots=True)
class MicrosoftCloudRequest:
    service: MicrosoftService
    method: str
    path: str
    permission_profile_name: str
    mode: MicrosoftOperationMode = MicrosoftOperationMode.READ
    query: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        method = self.method.strip().upper()
        if method not in _ALLOWED_METHODS:
            raise ValueError("Unsupported Microsoft HTTP method.")
        if not self.path.startswith("/"):
            raise ValueError("Microsoft request path must begin with '/'.")
        if "//" in self.path or ".." in self.path:
            raise ValueError("Microsoft request path contains an unsafe segment.")
        if "?" in self.path or "#" in self.path:
            raise ValueError(
                "Query strings and fragments must not be embedded in the Microsoft request path."
            )
        if len(self.path) > 2048:
            raise ValueError("Microsoft request path exceeds the governed length bound.")

        if self.query is not None:
            if len(self.query) > 16:
                raise ValueError("Microsoft request query exceeds the governed key bound.")
            for raw_key, raw_value in self.query.items():
                key = str(raw_key).strip()
                value = str(raw_value)
                if key not in _ALLOWED_QUERY_KEYS:
                    raise ValueError(f"Unsupported Microsoft query option: {key!r}.")
                if not value or len(value) > 4096:
                    raise ValueError(
                        f"Microsoft query option {key!r} is empty or exceeds the governed length bound."
                    )
                if any(ord(char) < 32 for char in value):
                    raise ValueError(
                        f"Microsoft query option {key!r} contains control characters."
                    )

        object.__setattr__(self, "method", method)


@dataclass(frozen=True, slots=True)
class GovernedMicrosoftRequest:
    url: str
    method: str
    service: MicrosoftService
    provider_name: str
    permission_profile: MicrosoftPermissionProfile
    mode: MicrosoftOperationMode


class MicrosoftRequestPolicyError(PermissionError):
    pass


def build_governed_request(request: MicrosoftCloudRequest) -> GovernedMicrosoftRequest:
    endpoint = endpoint_for(request.service)
    profile = permission_profile(request.permission_profile_name)
    validate_profile_for_services(profile, frozenset({request.service}))

    if request.mode not in endpoint.supported_modes:
        raise MicrosoftRequestPolicyError(
            f"Microsoft service {request.service.value!r} does not support requested mode "
            f"{request.mode.value!r}."
        )

    if _MODE_RANK[request.mode] > _MODE_RANK[profile.maximum_mode]:
        raise MicrosoftRequestPolicyError(
            f"Microsoft permission profile {profile.name!r} does not authorize requested mode "
            f"{request.mode.value!r}."
        )

    if request.mode is MicrosoftOperationMode.READ and request.method not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        raise MicrosoftRequestPolicyError(
            "Read mode permits only GET, HEAD, and OPTIONS requests."
        )

    version_prefix = f"/{endpoint.default_api_version}" if endpoint.default_api_version else ""
    url = f"{endpoint.base_url.rstrip('/')}{version_prefix}{request.path}"
    if request.query:
        url = f"{url}?{urlencode(dict(request.query))}"

    return GovernedMicrosoftRequest(
        url=url,
        method=request.method,
        service=request.service,
        provider_name=endpoint.provider_name,
        permission_profile=profile,
        mode=request.mode,
    )

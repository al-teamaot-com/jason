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
            raise ValueError("Query strings and fragments must not be embedded in the Microsoft request path.")
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
    validate_profile_for_services(profile, {request.service})

    if not endpoint.supports(request.mode):
        raise MicrosoftRequestPolicyError(
            f"Microsoft service {request.service.value!r} does not support requested mode {request.mode.value!r}."
        )

    if request.mode is MicrosoftOperationMode.READ and request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise MicrosoftRequestPolicyError("Read mode permits only GET, HEAD, and OPTIONS requests.")

    if request.mode is MicrosoftOperationMode.RECOMMEND and request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise MicrosoftRequestPolicyError("Recommend mode cannot perform Microsoft mutations.")

    if request.mode is MicrosoftOperationMode.WRITE_WITH_APPROVAL:
        if profile.maximum_mode is not MicrosoftOperationMode.WRITE_WITH_APPROVAL:
            raise MicrosoftRequestPolicyError(
                "Microsoft permission profile does not authorize write-with-approval operations."
            )

    if request.mode is MicrosoftOperationMode.BOUNDED_AUTOMATION:
        raise MicrosoftRequestPolicyError(
            "Microsoft bounded autonomous execution is not enabled by this foundation."
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

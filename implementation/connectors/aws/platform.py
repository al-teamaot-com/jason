from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .service_catalog import AwsService, service_profile


class AwsOperationMode(str, Enum):
    READ = 'read'
    RECOMMEND = 'recommend'
    WRITE_WITH_APPROVAL = 'write_with_approval'
    BOUNDED_AUTOMATION = 'bounded_automation'


class AwsRequestPolicyError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AwsCloudRequest:
    service: AwsService
    action: str
    account_id: str
    organization_id: str
    region: str | None = None
    mode: AwsOperationMode = AwsOperationMode.READ
    parameters: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if len(self.account_id) != 12 or not self.account_id.isdigit():
            raise ValueError('AWS account_id must be exactly 12 digits')
        if not self.organization_id.startswith('o-'):
            raise ValueError('AWS organization_id must begin with o-')
        if not self.action or not self.action.replace('_', '').isalnum():
            raise ValueError('AWS action contains invalid characters')
        profile = service_profile(self.service)
        if profile.regional and not (self.region and self.region.strip()):
            raise ValueError(f'AWS service {self.service.value} requires an explicit region')
        if not profile.regional and self.region is not None and not self.region.strip():
            raise ValueError('AWS region cannot be blank when supplied')


@dataclass(frozen=True, slots=True)
class GovernedAwsRequest:
    provider_name: str
    service: AwsService
    action: str
    account_id: str
    organization_id: str
    region: str | None
    mode: AwsOperationMode
    parameters: Mapping[str, object]


_ALLOWED_FOUNDATION_ACTIONS = {
    AwsOperationMode.READ,
    AwsOperationMode.RECOMMEND,
}


def build_governed_request(request: AwsCloudRequest) -> GovernedAwsRequest:
    profile = service_profile(request.service)

    if request.mode not in _ALLOWED_FOUNDATION_ACTIONS:
        raise AwsRequestPolicyError('AWS foundation enables only read/recommend modes')

    if request.action not in profile.read_actions:
        raise AwsRequestPolicyError(
            f'AWS action {request.action!r} is not in the governed read catalog for {request.service.value!r}'
        )

    if request.mode is AwsOperationMode.RECOMMEND and request.service is AwsService.STS and request.action == 'AssumeRole':
        raise AwsRequestPolicyError('STS AssumeRole is a credential bridge, not a recommendation capability')

    return GovernedAwsRequest(
        provider_name='aws',
        service=request.service,
        action=request.action,
        account_id=request.account_id,
        organization_id=request.organization_id,
        region=request.region,
        mode=request.mode,
        parameters=dict(request.parameters or {}),
    )

from __future__ import annotations

from dataclasses import dataclass


class AwsCredentialBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AwsRoleBinding:
    logical_name: str
    role_arn: str
    external_id_logical_name: str | None = None
    session_name_prefix: str = 'jason'
    duration_seconds: int = 900

    def __post_init__(self) -> None:
        if not self.logical_name.strip():
            raise AwsCredentialBindingError('logical_name is required')
        if not self.role_arn.startswith('arn:aws:iam::') or ':role/' not in self.role_arn:
            raise AwsCredentialBindingError('role_arn must be an AWS IAM role ARN')
        if not (900 <= self.duration_seconds <= 43200):
            raise AwsCredentialBindingError('duration_seconds must be between 900 and 43200')
        if not self.session_name_prefix.strip():
            raise AwsCredentialBindingError('session_name_prefix is required')


@dataclass(frozen=True, slots=True)
class AwsCredentialBinding:
    """Durable configuration for resolving runtime-only AWS STS credentials.

    No access key, secret access key, or session token is stored here. The
    durable secret/config boundary contains only role/bootstrap references.
    """

    account_id: str
    organization_id: str
    role: AwsRoleBinding
    home_region: str = 'us-east-1'

    def __post_init__(self) -> None:
        if len(self.account_id) != 12 or not self.account_id.isdigit():
            raise AwsCredentialBindingError('account_id must be exactly 12 digits')
        if not self.organization_id.startswith('o-'):
            raise AwsCredentialBindingError('organization_id must be an AWS Organizations ID')
        if not self.home_region.strip():
            raise AwsCredentialBindingError('home_region is required')

    @property
    def required_logical_secrets(self) -> tuple[str, ...]:
        items = [self.role.logical_name]
        if self.role.external_id_logical_name:
            items.append(self.role.external_id_logical_name)
        return tuple(items)

    @property
    def persists_runtime_credentials(self) -> bool:
        return False

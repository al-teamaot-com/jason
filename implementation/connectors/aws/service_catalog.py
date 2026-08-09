from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AwsService(str, Enum):
    STS = 'sts'
    ORGANIZATIONS = 'organizations'
    IAM = 'iam'
    CONFIG = 'config'
    SECURITY_HUB = 'securityhub'
    GUARDDUTY = 'guardduty'
    CLOUDTRAIL = 'cloudtrail'
    EC2 = 'ec2'
    S3 = 's3'
    RDS = 'rds'
    BACKUP = 'backup'
    SSM = 'ssm'


@dataclass(frozen=True, slots=True)
class AwsServiceProfile:
    service: AwsService
    regional: bool
    read_actions: tuple[str, ...]
    initial_enabled: bool = True


_PROFILES = {
    AwsService.STS: AwsServiceProfile(AwsService.STS, False, ('GetCallerIdentity', 'AssumeRole')),
    AwsService.ORGANIZATIONS: AwsServiceProfile(AwsService.ORGANIZATIONS, False, ('DescribeOrganization', 'ListAccounts', 'DescribeAccount', 'ListRoots', 'ListOrganizationalUnitsForParent')),
    AwsService.IAM: AwsServiceProfile(AwsService.IAM, False, ('GetAccountSummary', 'ListRoles', 'ListPolicies', 'ListAccountAliases')),
    AwsService.CONFIG: AwsServiceProfile(AwsService.CONFIG, True, ('ListDiscoveredResources', 'BatchGetResourceConfig', 'DescribeConfigurationRecorders')),
    AwsService.SECURITY_HUB: AwsServiceProfile(AwsService.SECURITY_HUB, True, ('DescribeHub', 'GetFindings', 'GetEnabledStandards')),
    AwsService.GUARDDUTY: AwsServiceProfile(AwsService.GUARDDUTY, True, ('ListDetectors', 'ListFindings', 'GetFindings')),
    AwsService.CLOUDTRAIL: AwsServiceProfile(AwsService.CLOUDTRAIL, True, ('DescribeTrails', 'GetTrailStatus', 'LookupEvents')),
    AwsService.EC2: AwsServiceProfile(AwsService.EC2, True, ('DescribeInstances', 'DescribeVolumes', 'DescribeVpcs', 'DescribeSecurityGroups')),
    AwsService.S3: AwsServiceProfile(AwsService.S3, False, ('ListBuckets', 'GetBucketLocation', 'GetBucketVersioning', 'GetPublicAccessBlock')),
    AwsService.RDS: AwsServiceProfile(AwsService.RDS, True, ('DescribeDBInstances', 'DescribeDBClusters', 'DescribeDBSnapshots')),
    AwsService.BACKUP: AwsServiceProfile(AwsService.BACKUP, True, ('ListBackupVaults', 'ListRecoveryPointsByBackupVault', 'ListBackupPlans')),
    AwsService.SSM: AwsServiceProfile(AwsService.SSM, True, ('DescribeInstanceInformation', 'ListComplianceItems', 'ListResourceComplianceSummaries')),
}


def service_profile(service: AwsService) -> AwsServiceProfile:
    return _PROFILES[service]

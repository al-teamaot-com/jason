from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest


class InformationAction(str, Enum):
    FETCH = "fetch"
    USE = "use"
    PROCESS = "process"
    RELEASE = "release"


class InformationHandlingClass(str, Enum):
    EXECUTION_ONLY = "execution_only"
    REASONING_ALLOWED_NON_RELEASABLE = "reasoning_allowed_non_releasable"
    DERIVED_OUTPUT_ONLY = "derived_output_only"
    RELEASABLE = "releasable"
    METADATA_ONLY = "metadata_only"


class InformationRemediation(str, Enum):
    NONE = "none"
    REQUEST_ACCESS = "request_access"
    REQUEST_APPROVAL = "request_approval"


@dataclass(frozen=True, slots=True)
class InformationAuthorizationDecision:
    action: InformationAction
    allowed: bool
    reason_code: str
    handling_class: InformationHandlingClass
    remediation: InformationRemediation = InformationRemediation.NONE
    policy_ids: tuple[str, ...] = ()
    authorization_basis: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code must be non-empty")
        if self.allowed and self.remediation is not InformationRemediation.NONE:
            raise ValueError("allowed decisions cannot require remediation")
        if not self.allowed and self.remediation is InformationRemediation.NONE:
            raise ValueError("denied decisions must identify a remediation path")


@dataclass(frozen=True, slots=True)
class InformationAuthorizationEnvelope:
    """Authorization state that travels with provider evidence.

    This envelope is control-plane metadata. It must not be embedded in user-facing
    evidence or treated as provider content. Unknown or incomplete authorization is
    intentionally non-releasable.
    """

    handling_class: InformationHandlingClass
    decisions: Mapping[InformationAction, InformationAuthorizationDecision] = field(
        default_factory=dict
    )
    source_provider: str | None = None
    source_resource_type: str | None = None
    source_scope: str | None = None

    def decision_for(self, action: InformationAction) -> InformationAuthorizationDecision | None:
        return self.decisions.get(action)

    def require_allowed(self, action: InformationAction) -> InformationAuthorizationDecision:
        decision = self.decision_for(action)
        if decision is None:
            return InformationAuthorizationDecision(
                action=action,
                allowed=False,
                reason_code=f"INFORMATION_{action.value.upper()}_AUTHORIZATION_UNKNOWN",
                handling_class=self.handling_class,
                remediation=InformationRemediation.REQUEST_ACCESS,
                authorization_basis=("fail_closed_missing_decision",),
            )
        return decision


@dataclass(frozen=True, slots=True)
class InformationReleaseDecision:
    allowed: bool
    output: Mapping[str, Any] = field(default_factory=dict)
    reason_code: str = "INFORMATION_RELEASE_ALLOWED"
    remediation: InformationRemediation = InformationRemediation.NONE
    handling_class: InformationHandlingClass = InformationHandlingClass.RELEASABLE
    policy_ids: tuple[str, ...] = ()
    authorization_basis: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code must be non-empty")
        if self.allowed and self.remediation is not InformationRemediation.NONE:
            raise ValueError("allowed releases cannot require remediation")
        if not self.allowed:
            if self.output:
                raise ValueError("denied releases must not contain user-facing output")
            if self.remediation is InformationRemediation.NONE:
                raise ValueError("denied releases must identify a remediation path")


class InformationReleaseAuthorizer(Protocol):
    def authorize_release(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        output: Mapping[str, Any],
        authorization: InformationAuthorizationEnvelope | None,
    ) -> InformationReleaseDecision: ...


@dataclass(frozen=True, slots=True)
class FailClosedInformationReleaseAuthorizer:
    """Release evidence only when every required information decision is explicit.

    Fetch permission is not release permission. Provider/service-account authority is
    not requester entitlement. Approval is not inferred. A missing decision, unknown
    provider permission, or non-releasable handling class results in a bounded denial.
    """

    def authorize_release(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        output: Mapping[str, Any],
        authorization: InformationAuthorizationEnvelope | None,
    ) -> InformationReleaseDecision:
        del request, resolution

        if authorization is None:
            return InformationReleaseDecision(
                allowed=False,
                reason_code="INFORMATION_AUTHORIZATION_REQUIRED",
                remediation=InformationRemediation.REQUEST_ACCESS,
                handling_class=InformationHandlingClass.EXECUTION_ONLY,
                authorization_basis=("fail_closed_missing_envelope",),
            )

        for action in (
            InformationAction.FETCH,
            InformationAction.USE,
            InformationAction.PROCESS,
            InformationAction.RELEASE,
        ):
            decision = authorization.require_allowed(action)
            if not decision.allowed:
                return InformationReleaseDecision(
                    allowed=False,
                    reason_code=decision.reason_code,
                    remediation=decision.remediation,
                    handling_class=authorization.handling_class,
                    policy_ids=decision.policy_ids,
                    authorization_basis=decision.authorization_basis,
                )

        if authorization.handling_class in {
            InformationHandlingClass.EXECUTION_ONLY,
            InformationHandlingClass.REASONING_ALLOWED_NON_RELEASABLE,
        }:
            return InformationReleaseDecision(
                allowed=False,
                reason_code="INFORMATION_CLASS_NOT_RELEASABLE",
                remediation=InformationRemediation.REQUEST_APPROVAL,
                handling_class=authorization.handling_class,
                authorization_basis=("handling_class_denies_release",),
            )

        if authorization.handling_class is InformationHandlingClass.DERIVED_OUTPUT_ONLY:
            return InformationReleaseDecision(
                allowed=False,
                reason_code="DERIVED_OUTPUT_TRANSFORMATION_REQUIRED",
                remediation=InformationRemediation.REQUEST_APPROVAL,
                handling_class=authorization.handling_class,
                authorization_basis=("raw_release_forbidden",),
            )

        return InformationReleaseDecision(
            allowed=True,
            output=dict(output),
            handling_class=authorization.handling_class,
            policy_ids=tuple(
                dict.fromkeys(
                    policy_id
                    for action in InformationAction
                    for policy_id in authorization.require_allowed(action).policy_ids
                )
            ),
            authorization_basis=tuple(
                dict.fromkeys(
                    basis
                    for action in InformationAction
                    for basis in authorization.require_allowed(action).authorization_basis
                )
            ),
        )

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ComponentVariablePolicy:
    name: str
    variable_type: str = "string"
    required: bool = False
    maximum_length: int = 20_000
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("component variable name must be non-empty")
        if self.variable_type not in {"string", "boolean", "date", "selection"}:
            raise ValueError("unsupported component variable type")
        if self.maximum_length < 1 or self.maximum_length > 20_000:
            raise ValueError("component variable maximum length must be 1..20000")
        if self.variable_type == "selection" and not self.allowed_values:
            raise ValueError("selection variables require allowed values")


@dataclass(frozen=True, slots=True)
class ComponentAllowlistEntry:
    allowlist_name: str
    canonical_component_id: str
    display_name: str
    provider_component_uid: str
    allowed_target_classes: frozenset[str]
    variable_policies: tuple[ComponentVariablePolicy, ...] = ()
    provider_metadata_fingerprint: str | None = None
    requires_per_run_approval: bool = True
    status: str = "active"

    def __post_init__(self) -> None:
        for value in (
            self.allowlist_name,
            self.canonical_component_id,
            self.display_name,
            self.provider_component_uid,
        ):
            if not value.strip():
                raise ValueError("component allowlist identifiers must be non-empty")
        if self.status not in {"active", "suspended", "retired"}:
            raise ValueError("unsupported component allowlist status")
        if not self.allowed_target_classes:
            raise ValueError("component allowlist must constrain target classes")
        names = [policy.name.casefold() for policy in self.variable_policies]
        if len(names) != len(set(names)):
            raise ValueError("component variable policies must have unique names")


class ComponentAllowlistResolver(Protocol):
    def resolve(self, allowlist_name: str) -> ComponentAllowlistEntry: ...


@dataclass(frozen=True, slots=True)
class StaticComponentAllowlist:
    entries: tuple[ComponentAllowlistEntry, ...]

    def resolve(self, allowlist_name: str) -> ComponentAllowlistEntry:
        requested = allowlist_name.strip().casefold()
        matches = [
            entry
            for entry in self.entries
            if entry.allowlist_name.casefold() == requested
        ]
        if len(matches) != 1:
            raise PermissionError("component allowlist entry is missing or ambiguous")
        return matches[0]


@dataclass(frozen=True, slots=True)
class PreparedQuickJobRequest:
    method: str
    path: str
    body: Mapping[str, Any]

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "method": self.method,
                    "path": self.path,
                    "body": self.body,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedComponentExecution:
    allowlist_entry: ComponentAllowlistEntry
    normalized_variables: Mapping[str, str]
    job_name: str
    provider_request: PreparedQuickJobRequest


class DattoRmmComponentExecutionPolicy:
    """Fail-closed source-only policy and request builder for Datto quick jobs.

    The object constructs a request but has no transport, credentials, or network
    method. It cannot execute a component. Runtime execution remains a separate,
    future activation step behind EXECUTE authority and a dedicated credential.
    """

    _SERVICE_DETAIL_DIAGNOSTIC_NAME = (
        "Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1"
    )

    def __init__(self, *, allowlist: ComponentAllowlistResolver) -> None:
        self._allowlist = allowlist

    @classmethod
    def _effective_variable_policies(
        cls,
        entry: ComponentAllowlistEntry,
    ) -> tuple[ComponentVariablePolicy, ...]:
        if entry.variable_policies:
            return entry.variable_policies

        # This is a source-controlled exception for one known diagnostic whose
        # only input selects the service to inspect. It does not grant arbitrary
        # PowerShell/CMD variables and unknown variable names still fail closed.
        if (
            entry.display_name.casefold()
            == cls._SERVICE_DETAIL_DIAGNOSTIC_NAME.casefold()
        ):
            return (
                ComponentVariablePolicy(
                    name="ServiceName",
                    variable_type="string",
                    required=False,
                    maximum_length=256,
                ),
            )

        return ()

    def prepare(
        self,
        *,
        allowlist_name: str,
        device_uid: str,
        device_class: str,
        component_uid: str,
        variables: Mapping[str, Any],
        job_name: str | None = None,
        observed_component_name: str | None = None,
        observed_metadata_fingerprint: str | None = None,
    ) -> PreparedComponentExecution:
        entry = self._allowlist.resolve(allowlist_name)
        if entry.status != "active":
            raise PermissionError("component allowlist entry is not active")

        target_uid = device_uid.strip()
        if not target_uid:
            raise ValueError("device_uid is required")

        target_class = device_class.strip().casefold()
        allowed_classes = {
            value.strip().casefold()
            for value in entry.allowed_target_classes
            if value.strip()
        }
        if not target_class or target_class not in allowed_classes:
            raise PermissionError("target device class is not allowed for this component")

        provider_uid = component_uid.strip()
        if not provider_uid or provider_uid != entry.provider_component_uid:
            raise PermissionError("component identity does not match the approved allowlist")

        if observed_component_name is not None:
            if observed_component_name.strip() != entry.display_name:
                raise PermissionError("component display name differs from the approved allowlist")

        expected_fingerprint = (entry.provider_metadata_fingerprint or "").strip()
        if expected_fingerprint:
            observed = (observed_metadata_fingerprint or "").strip()
            if not observed or observed != expected_fingerprint:
                raise PermissionError("component metadata fingerprint differs from the approved allowlist")

        normalized_variables = self._validate_variables(
            policies=self._effective_variable_policies(entry),
            supplied=variables,
        )

        normalized_job_name = (job_name or f"Jason - {entry.display_name}").strip()
        if not normalized_job_name:
            raise ValueError("job_name must be non-empty")
        if len(normalized_job_name) > 120:
            raise ValueError("job_name exceeds Jason's bounded quick-job name length")

        request = PreparedQuickJobRequest(
            method="PUT",
            path=f"/api/v2/device/{target_uid}/quickjob",
            body={
                "jobName": normalized_job_name,
                "jobComponent": {
                    "componentUid": provider_uid,
                    "variables": [
                        {"name": name, "value": value}
                        for name, value in normalized_variables.items()
                    ],
                },
            },
        )

        return PreparedComponentExecution(
            allowlist_entry=entry,
            normalized_variables=normalized_variables,
            job_name=normalized_job_name,
            provider_request=request,
        )

    @classmethod
    def _validate_variables(
        cls,
        *,
        policies: tuple[ComponentVariablePolicy, ...],
        supplied: Mapping[str, Any],
    ) -> Mapping[str, str]:
        if not isinstance(supplied, Mapping):
            raise ValueError("component variables must be a mapping")

        by_name = {policy.name.casefold(): policy for policy in policies}
        normalized: dict[str, str] = {}

        for supplied_name, value in supplied.items():
            if not isinstance(supplied_name, str) or not supplied_name.strip():
                raise ValueError("component variable names must be non-empty strings")
            policy = by_name.get(supplied_name.strip().casefold())
            if policy is None:
                raise PermissionError("component variable is not approved by the allowlist")
            normalized[policy.name] = cls._normalize_variable_value(policy, value)

        missing = [
            policy.name
            for policy in policies
            if policy.required and policy.name not in normalized
        ]
        if missing:
            raise ValueError("required component variables are missing")

        # Stable policy order makes approval/request digests deterministic.
        return {
            policy.name: normalized[policy.name]
            for policy in policies
            if policy.name in normalized
        }

    @staticmethod
    def _normalize_variable_value(
        policy: ComponentVariablePolicy,
        value: Any,
    ) -> str:
        if policy.variable_type == "boolean":
            if isinstance(value, bool):
                normalized = "true" if value else "false"
            elif isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
                normalized = value.strip().casefold()
            else:
                raise ValueError("boolean component variable must be true or false")
        elif policy.variable_type == "date":
            if not isinstance(value, str):
                raise ValueError("date component variable must use ISO date text")
            normalized = value.strip()
            try:
                date.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError("date component variable must use YYYY-MM-DD") from exc
        else:
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                raise ValueError("component variable must be a scalar value")
            normalized = str(value).strip()

        if len(normalized) > policy.maximum_length:
            raise ValueError("component variable exceeds approved maximum length")

        if policy.variable_type == "selection" and normalized not in policy.allowed_values:
            raise PermissionError("component variable value is not allowlisted")

        return normalized

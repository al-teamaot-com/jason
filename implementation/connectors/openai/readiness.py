"""OpenAI capability-readiness probe.

Provider-specific API details belong here at the connector boundary.

This adapter returns Jason's provider-neutral readiness observation and has no
execution authority beyond its bounded diagnostic probe.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from orchestrator.provider_capability_readiness import (
    ProviderCapabilityObservation,
    ReadinessDimension,
    ReadinessReason,
)


OPENAI_RESPONSES_ENDPOINT = (
    "https://api.openai.com/v1/responses"
)


@dataclass(frozen=True, slots=True)
class OpenAIProviderFailure:
    status_code: int | None
    error_type: str | None
    error_code: str | None


def normalize_openai_failure(
    *,
    status_code: int | None,
    error_type: str | None = None,
    error_code: str | None = None,
) -> ReadinessReason:
    """Translate OpenAI-native failure evidence into Jason reason vocabulary."""

    normalized_type = str(
        error_type or ""
    ).strip().casefold()

    normalized_code = str(
        error_code or ""
    ).strip().casefold()

    if (
        normalized_type == "insufficient_quota"
        or normalized_code
        in {
            "credit_balance_exhausted",
            "insufficient_quota",
        }
    ):
        return ReadinessReason.QUOTA_EXHAUSTED

    if status_code == 401:
        return ReadinessReason.AUTHENTICATION_FAILED

    if status_code == 403:
        return ReadinessReason.PERMISSION_DENIED

    if status_code == 429:
        return ReadinessReason.RATE_LIMITED

    if status_code in {
        408,
        504,
    }:
        return ReadinessReason.PROVIDER_TIMEOUT

    if status_code == 400:
        return ReadinessReason.CONTRACT_INCOMPATIBLE

    if (
        status_code is not None
        and status_code >= 500
    ):
        return ReadinessReason.PROVIDER_UNAVAILABLE

    return ReadinessReason.UNKNOWN_PROVIDER_FAILURE


@dataclass(frozen=True, slots=True)
class OpenAIResponsesReadinessProbe:
    """Perform a minimum bounded Responses API capability proof."""

    api_key: str = field(repr=False)
    model: str = ""
    timeout_seconds: float = 20.0
    endpoint: str = OPENAI_RESPONSES_ENDPOINT

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError(
                "OpenAI readiness probe requires API key"
            )

        if not self.model.strip():
            raise ValueError(
                "OpenAI readiness probe requires model"
            )

        if (
            self.timeout_seconds <= 0
            or self.timeout_seconds > 60
        ):
            raise ValueError(
                "OpenAI readiness timeout is invalid"
            )

    def observe(
        self,
        *,
        provider_id: str,
        capability_name: str,
        component_healthy: bool = True,
    ) -> ProviderCapabilityObservation:
        observed_at = datetime.now(
            timezone.utc
        )

        component = ReadinessDimension(
            checked=True,
            healthy=component_healthy,
            reason=(
                ReadinessReason.NONE
                if component_healthy
                else ReadinessReason.RUNTIME_UNHEALTHY
            ),
        )

        if not component_healthy:
            return ProviderCapabilityObservation(
                provider_id=provider_id,
                capability_name=capability_name,
                observed_at=observed_at,
                component=component,
                reachability=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                authentication=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                capability=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                evidence_source=(
                    "openai-responses-readiness-probe"
                ),
                probe_version="1",
            )

        try:
            self._resolve_endpoint()
        except OSError:
            return self._failure_observation(
                provider_id=provider_id,
                capability_name=capability_name,
                observed_at=observed_at,
                component=component,
                reachability=ReadinessDimension(
                    checked=True,
                    healthy=False,
                    reason=(
                        ReadinessReason.DEPENDENCY_UNREACHABLE
                    ),
                ),
                authentication=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                capability=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
            )

        reachability = ReadinessDimension(
            checked=True,
            healthy=True,
        )

        try:
            result = self._request()
        except TimeoutError:
            return self._failure_observation(
                provider_id=provider_id,
                capability_name=capability_name,
                observed_at=observed_at,
                component=component,
                reachability=reachability,
                authentication=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                capability=ReadinessDimension(
                    checked=True,
                    healthy=False,
                    reason=ReadinessReason.PROVIDER_TIMEOUT,
                ),
            )
        except urllib.error.URLError as error:
            if isinstance(
                error.reason,
                (
                    TimeoutError,
                    socket.timeout,
                ),
            ):
                reason = ReadinessReason.PROVIDER_TIMEOUT
            else:
                reason = (
                    ReadinessReason.DEPENDENCY_UNREACHABLE
                )

            return self._failure_observation(
                provider_id=provider_id,
                capability_name=capability_name,
                observed_at=observed_at,
                component=component,
                reachability=ReadinessDimension(
                    checked=True,
                    healthy=(
                        reason
                        is not ReadinessReason.DEPENDENCY_UNREACHABLE
                    ),
                    reason=(
                        ReadinessReason.NONE
                        if reason
                        is not ReadinessReason.DEPENDENCY_UNREACHABLE
                        else reason
                    ),
                ),
                authentication=ReadinessDimension(
                    checked=False,
                    healthy=None,
                ),
                capability=ReadinessDimension(
                    checked=(
                        reason
                        is ReadinessReason.PROVIDER_TIMEOUT
                    ),
                    healthy=(
                        False
                        if reason
                        is ReadinessReason.PROVIDER_TIMEOUT
                        else None
                    ),
                    reason=(
                        reason
                        if reason
                        is ReadinessReason.PROVIDER_TIMEOUT
                        else ReadinessReason.NONE
                    ),
                ),
            )

        if isinstance(
            result,
            OpenAIProviderFailure,
        ):
            reason = normalize_openai_failure(
                status_code=result.status_code,
                error_type=result.error_type,
                error_code=result.error_code,
            )

            authentication_failure = (
                reason
                is ReadinessReason.AUTHENTICATION_FAILED
            )

            permission_failure = (
                reason
                is ReadinessReason.PERMISSION_DENIED
            )

            if authentication_failure:
                authentication = ReadinessDimension(
                    checked=True,
                    healthy=False,
                    reason=reason,
                )

                capability = ReadinessDimension(
                    checked=False,
                    healthy=None,
                )

            elif permission_failure:
                authentication = ReadinessDimension(
                    checked=True,
                    healthy=True,
                )

                capability = ReadinessDimension(
                    checked=True,
                    healthy=False,
                    reason=reason,
                )

            else:
                authentication = ReadinessDimension(
                    checked=True,
                    healthy=True,
                )

                capability = ReadinessDimension(
                    checked=True,
                    healthy=False,
                    reason=reason,
                )

            safe_metadata = {}

            if result.error_type:
                safe_metadata[
                    "provider_error_type"
                ] = result.error_type

            if result.error_code:
                safe_metadata[
                    "provider_error_code"
                ] = result.error_code

            return ProviderCapabilityObservation(
                provider_id=provider_id,
                capability_name=capability_name,
                observed_at=observed_at,
                component=component,
                reachability=reachability,
                authentication=authentication,
                capability=capability,
                evidence_source=(
                    "openai-responses-readiness-probe"
                ),
                probe_version="1",
                provider_status_code=(
                    str(result.status_code)
                    if result.status_code is not None
                    else None
                ),
                safe_metadata=safe_metadata,
            )

        return ProviderCapabilityObservation(
            provider_id=provider_id,
            capability_name=capability_name,
            observed_at=observed_at,
            component=component,
            reachability=reachability,
            authentication=ReadinessDimension(
                checked=True,
                healthy=True,
            ),
            capability=ReadinessDimension(
                checked=True,
                healthy=True,
            ),
            evidence_source=(
                "openai-responses-readiness-probe"
            ),
            probe_version="1",
            provider_status_code="200",
        )

    def _resolve_endpoint(
        self,
    ) -> None:
        parsed = urllib.parse.urlparse(
            self.endpoint
        )

        host = parsed.hostname

        if not host:
            raise OSError(
                "OpenAI readiness endpoint has no host"
            )

        socket.getaddrinfo(
            host,
            443,
            type=socket.SOCK_STREAM,
        )

    def _request(
        self,
    ) -> Mapping[str, object] | OpenAIProviderFailure:
        payload = {
            "model":
                self.model,
            "instructions":
                "Return the bounded diagnostic status.",
            "input":
                "Return status ok.",
            "text": {
                "format": {
                    "type":
                        "json_schema",
                    "name":
                        "jason_provider_readiness",
                    "strict":
                        True,
                    "schema": {
                        "type":
                            "object",
                        "additionalProperties":
                            False,
                        "properties": {
                            "status": {
                                "type":
                                    "string",
                                "enum": [
                                    "ok"
                                ],
                            },
                        },
                        "required": [
                            "status"
                        ],
                    },
                },
            },
            "max_output_tokens":
                32,
            "store":
                False,
        }

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={
                "Authorization":
                    "Bearer " + self.api_key,
                "Content-Type":
                    "application/json",
                "Accept":
                    "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read()

                if not raw:
                    return {}

                decoded = json.loads(
                    raw.decode("utf-8")
                )

                if isinstance(
                    decoded,
                    Mapping,
                ):
                    return dict(
                        decoded
                    )

                return {}

        except urllib.error.HTTPError as error:
            error_type = None
            error_code = None

            try:
                raw = error.read().decode(
                    "utf-8",
                    errors="replace",
                )

                decoded = json.loads(
                    raw
                )

                if isinstance(
                    decoded,
                    Mapping,
                ):
                    provider_error = decoded.get(
                        "error"
                    )

                    if isinstance(
                        provider_error,
                        Mapping,
                    ):
                        raw_type = provider_error.get(
                            "type"
                        )

                        raw_code = provider_error.get(
                            "code"
                        )

                        if raw_type is not None:
                            error_type = str(
                                raw_type
                            )[:128]

                        if raw_code is not None:
                            error_code = str(
                                raw_code
                            )[:128]

            except Exception:
                pass

            return OpenAIProviderFailure(
                status_code=int(
                    error.code
                ),
                error_type=error_type,
                error_code=error_code,
            )

    def _failure_observation(
        self,
        *,
        provider_id: str,
        capability_name: str,
        observed_at: datetime,
        component: ReadinessDimension,
        reachability: ReadinessDimension,
        authentication: ReadinessDimension,
        capability: ReadinessDimension,
    ) -> ProviderCapabilityObservation:
        return ProviderCapabilityObservation(
            provider_id=provider_id,
            capability_name=capability_name,
            observed_at=observed_at,
            component=component,
            reachability=reachability,
            authentication=authentication,
            capability=capability,
            evidence_source=(
                "openai-responses-readiness-probe"
            ),
            probe_version="1",
        )

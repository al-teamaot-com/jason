from __future__ import annotations

from kernel.execution_policy import (
    ExecutionCandidate,
    ExecutionMode,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderHealth,
    ProviderType,
)


class ProviderCandidateTranslator:
    """Translate governed provider records into policy candidates."""

    @staticmethod
    def translate(
        provider: ExecutionProvider,
        *,
        requested_mode: str,
        requested_region: str | None,
    ) -> ExecutionCandidate:
        try:
            execution_mode = ExecutionMode(requested_mode)
        except ValueError as error:
            raise ValueError(
                f"Unsupported execution mode: {requested_mode}"
            ) from error

        if requested_mode not in provider.execution_modes:
            raise ValueError(
                "Provider does not support the requested execution mode: "
                f"{provider.provider_id}"
            )

        region = ProviderCandidateTranslator._resolve_region(
            provider,
            requested_region=requested_region,
        )

        return ExecutionCandidate(
            execution_mode=execution_mode,
            provider_id=provider.provider_id,
            model_id=provider.metadata.get("model_id"),
            region=region,
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_attempts=1,
            deterministic_quality_sufficient=(
                provider.provider_type is ProviderType.DETERMINISTIC
            ),
            approved=(
                provider.approval_status
                in {
                    ProviderApproval.APPROVED,
                    ProviderApproval.PILOT,
                }
            ),
            healthy=(
                provider.health_status
                in {
                    ProviderHealth.HEALTHY,
                    ProviderHealth.WARNING,
                }
            ),
            supports_classifications=(
                provider.supported_classifications
            ),
        )

    @staticmethod
    def translate_all(
        providers: tuple[ExecutionProvider, ...],
        *,
        requested_mode: str,
        requested_region: str | None,
    ) -> tuple[ExecutionCandidate, ...]:
        return tuple(
            ProviderCandidateTranslator.translate(
                provider,
                requested_mode=requested_mode,
                requested_region=requested_region,
            )
            for provider in sorted(
                providers,
                key=lambda item: item.provider_id,
            )
        )

    @staticmethod
    def _resolve_region(
        provider: ExecutionProvider,
        *,
        requested_region: str | None,
    ) -> str | None:
        if requested_region is not None:
            if (
                provider.regions
                and requested_region not in provider.regions
            ):
                raise ValueError(
                    "Provider does not support the requested region: "
                    f"{provider.provider_id}"
                )
            return requested_region

        if not provider.regions:
            return None

        return sorted(provider.regions)[0]

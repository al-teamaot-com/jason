"""Standalone governed OpenAI readiness check.

This script is intentionally outside the live Teams request path.

It:
- resolves the existing OpenBao OpenAI credential;
- performs a bounded provider capability probe;
- persists readiness state;
- creates transition-based alert events;
- prints safe operational classification only.

It does not send alerts.
"""

from __future__ import annotations

import os
from pathlib import Path

from connectors.core.contracts import (
    ConnectorContext,
)
from connectors.core.openbao_secrets import (
    OpenBaoSecretResolver,
)
from connectors.openai.readiness import (
    OpenAIResponsesReadinessProbe,
)
from jason_runtime.composition import (
    RuntimeSettings,
)
from orchestrator.provider_capability_readiness_store import (
    SQLiteProviderCapabilityReadinessStore,
)
from orchestrator.provider_readiness_runner import (
    ProviderCapabilityReadinessRunner,
)


def main() -> int:
    settings = RuntimeSettings.from_env()

    db_path = Path(
        os.getenv(
            "JASON_PROVIDER_READINESS_DB",
            "/var/lib/jason/openclaw/provider-readiness.sqlite3",
        )
    )

    resolver = OpenBaoSecretResolver(
        base_url=settings.openbao_url,
        role_id_path=settings.openai_openbao_role_id_path,
        secret_id_path=settings.openai_openbao_secret_id_path,
    )

    values = {}

    try:
        values = dict(
            resolver.resolve(
                "openai.semantic_intent",
                ConnectorContext(
                    correlation_id=(
                        "provider-readiness-openai"
                    ),
                    principal_id="jason-runtime",
                    organization_id="aot",
                    client_id=None,
                    capability=(
                        "conversation.intent.interpret"
                    ),
                    mode="observe",
                ),
            )
        )

        api_key = str(
            values["api_key"]
        ).strip()

        probe = OpenAIResponsesReadinessProbe(
            api_key=api_key,
            model=settings.conversation_hosted_kernel_model,
            timeout_seconds=20,
        )

        store = SQLiteProviderCapabilityReadinessStore(
            db_path
        )

        try:
            runner = ProviderCapabilityReadinessRunner(
                store=store
            )

            result = runner.run_once(
                probe=probe,
                provider_id=(
                    "provider.openai-conversation-kernel"
                ),
                capability_name=(
                    "conversation.intent.interpret"
                ),
                component_healthy=True,
            )

            print(
                "PROVIDER="
                + result.current.provider_id
            )

            print(
                "CAPABILITY="
                + result.current.capability_name
            )

            print(
                "READINESS_STATE="
                + result.current.state.value.upper()
            )

            print(
                "READINESS_REASON="
                + result.current.reason.value
            )

            print(
                "PROVIDER_STATUS="
                + str(
                    result.current.provider_status_code
                    or ""
                )
            )

            print(
                "STATE_CHANGED="
                + str(
                    result.transition.changed
                ).upper()
            )

            print(
                "SHOULD_ALERT="
                + str(
                    result.transition.should_alert
                ).upper()
            )

            if result.alert_event is not None:
                print(
                    "ALERT_EVENT_KIND="
                    + result.alert_event.event_kind
                )

        finally:
            store.close()

    finally:
        values.clear()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

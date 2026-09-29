from __future__ import annotations

from dataclasses import replace
import time

from .composition import RuntimeSettings, build_runtime_application


def autonomy_maintenance_enabled(settings: RuntimeSettings) -> bool:
    return bool(
        settings.autonomy_worker_enabled
        or settings.autonomy_shadow_enabled
        or settings.autonomy_review_enabled
        or settings.support_repair_autonomy_enabled
    )


def http_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Return settings for the request-serving process with autonomy maintenance disabled."""

    return replace(
        settings,
        autonomy_worker_enabled=False,
        autonomy_shadow_enabled=False,
        autonomy_review_enabled=False,
        support_repair_autonomy_enabled=False,
    )


def run_autonomy_maintenance_process(
    settings: RuntimeSettings,
    *,
    idle_sleep_seconds: float = 0.5,
) -> None:
    """Own autonomy maintenance in a separate process with fresh SQLite connections."""

    application = build_runtime_application(settings)
    maintenance = application.maintenance
    if maintenance is None:
        return

    while True:
        try:
            maintenance.tick()
        except Exception:
            # Match the runtime server's existing fail-closed maintenance behavior:
            # one failed cycle must not terminate the long-lived maintenance process.
            pass
        time.sleep(max(0.05, float(idle_sleep_seconds)))

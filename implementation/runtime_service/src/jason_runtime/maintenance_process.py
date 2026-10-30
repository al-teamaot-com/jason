from __future__ import annotations

from dataclasses import replace
import logging
import time

from .composition import RuntimeSettings, build_runtime_application


logger = logging.getLogger(__name__)


def autonomy_maintenance_enabled(settings: RuntimeSettings) -> bool:
    return bool(
        settings.autonomy_worker_enabled
        or settings.autonomy_shadow_enabled
        or settings.autonomy_review_enabled
        or settings.support_repair_autonomy_enabled
        or (settings.universal_approval_mode == "enforced" and settings.universal_approval_worker_enabled)
        or (settings.owner_uat_mode == "nonexecuting_test_only" and settings.owner_uat_worker_enabled)
    )


def http_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Return settings for the request-serving process with autonomy maintenance disabled."""

    return replace(
        settings,
        autonomy_worker_enabled=False,
        autonomy_shadow_enabled=False,
        # Keep the Teams response endpoint while disabling duplicate card
        # generation: HTTP and maintenance use the same durable ledger.
        playbook_approval_ingress_enabled=(
            settings.autonomy_review_enabled or settings.playbook_approval_ingress_enabled
        ),
        autonomy_review_enabled=False,
        support_repair_autonomy_enabled=False,
        universal_approval_worker_enabled=False,
        release_mobile_approval_worker_enabled=False,
        owner_uat_worker_enabled=False,
    )


def ticket_worker_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Ticket process owns one ticket-admission ledger and no auxiliary loops."""
    return replace(
        settings, autonomy_worker_enabled=True, autonomy_shadow_enabled=False,
        autonomy_review_enabled=False, support_repair_autonomy_enabled=False,
    )


def auxiliary_maintenance_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Avoid duplicate ticket admission in the auxiliary maintenance process."""
    return replace(settings, autonomy_worker_enabled=False)


def run_autonomy_maintenance_process(
    settings: RuntimeSettings,
    *,
    idle_sleep_seconds: float = 0.5,
    maintenance_profile: str = "all",
) -> None:
    """Own autonomy maintenance in a separate process with fresh SQLite connections."""

    application = (
        build_runtime_application(settings) if maintenance_profile == "all"
        else build_runtime_application(settings, maintenance_profile=maintenance_profile)
    )
    maintenance = application.maintenance
    if maintenance is None:
        return

    while True:
        try:
            maintenance.tick()
        except Exception:
            # Match the runtime server's existing fail-closed maintenance behavior:
            # one failed cycle must not terminate the long-lived maintenance process.
            logger.exception("Autonomy maintenance cycle failed; retrying on next tick")
        time.sleep(max(0.05, float(idle_sleep_seconds)))

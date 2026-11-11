"""Standalone, non-HTTP ticket-processing service entrypoint (PMv4 preprod).

Run only inside a separately controlled Ticket Processing Core lifecycle.
No production service/timer is installed by this source module. This is NOT
an approval to migrate or to run alongside the existing embedded worker.
"""
from __future__ import annotations

from multiprocessing import get_context
import signal
from threading import Event

from .autonomy_worker_supervisor import TicketWorkerSupervisor, read_worker_heartbeat
from .composition import RuntimeSettings
from .maintenance_process import run_autonomy_maintenance_process, ticket_worker_runtime_settings
from .ticket_worker_ownership import exclusive_ticket_worker_owner


def standalone_ticket_worker(settings: RuntimeSettings, *, stop: Event | None = None) -> None:
    """Own only ticket dispatch, not PM development/release or HTTP serving."""
    settings.validate()
    if not settings.autonomy_worker_enabled or settings.ticket_worker_hosting != "external":
        raise RuntimeError("TICKET_CORE_EXTERNAL_MODE_NOT_AUTHORIZED")
    ticket_settings = ticket_worker_runtime_settings(settings)
    context = get_context("spawn")

    def factory():
        return context.Process(
            target=run_autonomy_maintenance_process,
            args=(ticket_settings,),
            kwargs={"maintenance_profile": "ticket_worker"},
            name="jason-ticket-autonomy",
            daemon=True,
        )

    with exclusive_ticket_worker_owner(settings.autonomy_worker_db):
        supervisor = TicketWorkerSupervisor(
            process_factory=factory,
            heartbeat_reader=lambda: read_worker_heartbeat(settings.autonomy_worker_db),
            interval_seconds=settings.autonomy_worker_interval_seconds,
        )
        shutdown = stop or Event()
        supervisor.start()
        try:
            supervisor.monitor_forever(shutdown)
        finally:
            supervisor.stop()


def main() -> None:
    stop = Event()

    def stop_request(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, stop_request)
    signal.signal(signal.SIGINT, stop_request)
    standalone_ticket_worker(RuntimeSettings.from_env(), stop=stop)


if __name__ == "__main__":
    main()

from __future__ import annotations

from contextlib import nullcontext
from multiprocessing import get_context
from threading import Event, Thread

from .composition import RuntimeSettings, build_runtime_application
from .maintenance_process import (
    auxiliary_maintenance_runtime_settings,
    autonomy_maintenance_enabled,
    http_runtime_settings,
    run_autonomy_maintenance_process,
    ticket_worker_runtime_settings,
)
from .autonomy_worker_supervisor import TicketWorkerSupervisor, read_worker_heartbeat
from .ticket_worker_ownership import exclusive_ticket_worker_owner
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    settings.validate()
    # The default embedded worker preserves existing production behavior.
    # An external worker is supervised by its OWN service; the HTTP/PM
    # lifecycle must never spawn a second ticket-dispatch owner.
    ownership = (
        exclusive_ticket_worker_owner(settings.autonomy_worker_db)
        if settings.autonomy_worker_enabled and settings.ticket_worker_hosting == "embedded"
        else nullcontext()
    )
    with ownership:
        _run_hosted_runtime(settings)


def _run_hosted_runtime(settings: RuntimeSettings) -> None:
    processes = []
    supervisor = None
    stop = None
    monitor = None
    serving_settings = settings

    if autonomy_maintenance_enabled(settings):
        context = get_context("spawn")
        if settings.autonomy_worker_enabled and settings.ticket_worker_hosting == "embedded":
            ticket_settings = ticket_worker_runtime_settings(settings)

            def factory():
                return context.Process(
                    target=run_autonomy_maintenance_process,
                    args=(ticket_settings,),
                    kwargs={"maintenance_profile": "ticket_worker"},
                    name="jason-ticket-autonomy",
                    daemon=True,
                )

            supervisor = TicketWorkerSupervisor(
                process_factory=factory,
                heartbeat_reader=lambda: read_worker_heartbeat(ticket_settings.autonomy_worker_db),
                interval_seconds=ticket_settings.autonomy_worker_interval_seconds,
            )
            supervisor.start()
            stop = Event()
            monitor = Thread(
                target=supervisor.monitor_forever, args=(stop,),
                name="jason-ticket-autonomy-supervisor", daemon=True,
            )
            monitor.start()

        auxiliary = context.Process(
            target=run_autonomy_maintenance_process,
            args=(auxiliary_maintenance_runtime_settings(settings),),
            kwargs={"maintenance_profile": "auxiliary"},
            name="jason-autonomy-auxiliary", daemon=True,
        )
        auxiliary.start()
        processes.append(auxiliary)
        serving_settings = http_runtime_settings(settings)

    application = build_runtime_application(
        serving_settings,
        health_probe=supervisor.health_status if supervisor is not None else None,
    )
    try:
        serve(application, host=serving_settings.host, port=serving_settings.port)
    finally:
        if stop is not None:
            stop.set()
        if monitor is not None:
            monitor.join(timeout=5)
        if supervisor is not None:
            supervisor.stop()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


if __name__ == "__main__":
    main()

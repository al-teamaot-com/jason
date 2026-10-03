from __future__ import annotations

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
from .autonomy_worker_supervisor import (
    TicketWorkerSupervisor,
    read_worker_heartbeat,
)
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    maintenance_processes = []
    ticket_supervisor = None
    ticket_supervisor_stop = None
    ticket_supervisor_thread = None
    serving_settings = settings

    if autonomy_maintenance_enabled(settings):
        # Use spawn so each maintenance role creates independent SQLite connections
        # instead of inheriting thread/process-bound runtime objects from HTTP.
        # Operational ticket admission is isolated from model/support/shadow work so
        # an unrelated slow maintenance task cannot starve the ticket control loop.
        context = get_context("spawn")
        if settings.autonomy_worker_enabled:
            ticket_settings = ticket_worker_runtime_settings(settings)

            def ticket_process_factory():
                return context.Process(
                    target=run_autonomy_maintenance_process,
                    args=(ticket_settings,),
                    kwargs={"maintenance_profile": "ticket_worker"},
                    name="jason-ticket-autonomy",
                    daemon=True,
                )

            ticket_supervisor = TicketWorkerSupervisor(
                process_factory=ticket_process_factory,
                heartbeat_reader=lambda: read_worker_heartbeat(
                    ticket_settings.autonomy_worker_db
                ),
                interval_seconds=ticket_settings.autonomy_worker_interval_seconds,
            )
            ticket_supervisor.start()
            ticket_supervisor_stop = Event()
            ticket_supervisor_thread = Thread(
                target=ticket_supervisor.monitor_forever,
                args=(ticket_supervisor_stop,),
                name="jason-ticket-autonomy-supervisor",
                daemon=True,
            )
            ticket_supervisor_thread.start()

        auxiliary_settings = auxiliary_maintenance_runtime_settings(settings)
        auxiliary_process = context.Process(
            target=run_autonomy_maintenance_process,
            args=(auxiliary_settings,),
            kwargs={"maintenance_profile": "auxiliary"},
            name="jason-autonomy-auxiliary",
            daemon=True,
        )
        auxiliary_process.start()
        maintenance_processes.append(auxiliary_process)
        serving_settings = http_runtime_settings(settings)

    application = build_runtime_application(
        serving_settings,
        health_probe=(
            ticket_supervisor.health_status
            if ticket_supervisor is not None
            else None
        ),
    )
    try:
        serve(application, host=serving_settings.host, port=serving_settings.port)
    finally:
        if ticket_supervisor_stop is not None:
            ticket_supervisor_stop.set()
        if ticket_supervisor_thread is not None:
            ticket_supervisor_thread.join(timeout=5)
        if ticket_supervisor is not None:
            ticket_supervisor.stop()
        for maintenance_process in maintenance_processes:
            if maintenance_process.is_alive():
                maintenance_process.terminate()
                maintenance_process.join(timeout=5)


if __name__ == "__main__":
    main()

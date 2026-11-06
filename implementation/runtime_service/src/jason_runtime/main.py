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
from .autonomy_worker_supervisor import TicketWorkerSupervisor, read_worker_heartbeat
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    processes = []
    supervisor = None
    stop = None
    monitor = None
    serving_settings = settings

    if autonomy_maintenance_enabled(settings):
        context = get_context("spawn")
        if settings.autonomy_worker_enabled:
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

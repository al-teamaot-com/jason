from __future__ import annotations

from multiprocessing import get_context

from .composition import RuntimeSettings, build_runtime_application
from .maintenance_process import (
    autonomy_maintenance_enabled,
    http_runtime_settings,
    run_autonomy_maintenance_process,
)
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    maintenance_process = None
    serving_settings = settings

    if autonomy_maintenance_enabled(settings):
        # Use spawn so the maintenance process creates its own SQLite connections
        # instead of inheriting thread/process-bound runtime objects from the HTTP
        # process. The HTTP process remains single-threaded for request handling.
        context = get_context("spawn")
        maintenance_process = context.Process(
            target=run_autonomy_maintenance_process,
            args=(settings,),
            name="jason-autonomy-maintenance",
            daemon=True,
        )
        maintenance_process.start()
        serving_settings = http_runtime_settings(settings)

    application = build_runtime_application(serving_settings)
    try:
        serve(application, host=serving_settings.host, port=serving_settings.port)
    finally:
        if maintenance_process is not None and maintenance_process.is_alive():
            maintenance_process.terminate()
            maintenance_process.join(timeout=5)


if __name__ == "__main__":
    main()

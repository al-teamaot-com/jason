from __future__ import annotations

from .composition import RuntimeSettings, build_runtime_application
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    # Runtime composition has one authority:
    # build_runtime_application() constructs the governed conversation
    # front door exactly once. main.py only serves that application.
    application = build_runtime_application(settings)
    serve(application, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

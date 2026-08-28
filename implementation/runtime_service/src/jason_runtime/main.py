from __future__ import annotations

from .composition import RuntimeSettings, build_runtime_application
from .conversation_experience_application import apply_conversation_experience_cutover
from .server import serve


def main() -> None:
    settings = RuntimeSettings.from_env()
    application = apply_conversation_experience_cutover(
        build_runtime_application(settings),
        runtime_settings=settings,
    )
    serve(application, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

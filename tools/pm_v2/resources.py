from __future__ import annotations

from pathlib import Path

from .config import PMV2Config


PRLIMIT = Path("/usr/bin/prlimit")


def wrap_subprocess_command(
    config: PMV2Config,
    command: list[str],
) -> list[str]:
    limits = []
    if config.subprocess_memory_mb:
        value = config.subprocess_memory_mb * 1024 * 1024
        limits.append(f"--as={value}:{value}")
    if config.subprocess_cpu_seconds:
        value = config.subprocess_cpu_seconds
        limits.append(f"--cpu={value}:{value}")
    if config.subprocess_open_files:
        value = config.subprocess_open_files
        limits.append(f"--nofile={value}:{value}")
    if not limits:
        return command
    if not PRLIMIT.is_file():
        raise RuntimeError("PM_V2_PRLIMIT_UNAVAILABLE")
    return [str(PRLIMIT), *limits, "--", *command]

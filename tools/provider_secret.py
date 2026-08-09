#!/usr/bin/env python3
"""Canonical operator entrypoint for Project Jason provider-secret lifecycle."""
from __future__ import annotations

try:
    from tools.provider_secret_lifecycle import main
except ModuleNotFoundError:
    from provider_secret_lifecycle import main


if __name__ == "__main__":
    raise SystemExit(main())

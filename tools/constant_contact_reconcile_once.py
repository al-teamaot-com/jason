#!/usr/bin/env python3
"""Compatibility CLI for the container-packaged GET-only readback entrypoint.

No direct provider access or additional scheduler is created here.
"""
from __future__ import annotations

from jason_runtime.constant_contact_reconcile_entrypoint import (
    PROFILE, PROFILE_ENV, run_cycle, main,
)

if __name__ == "__main__":
    import sys
    sys.exit(main())

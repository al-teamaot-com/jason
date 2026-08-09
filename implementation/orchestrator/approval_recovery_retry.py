"""Governed retry execution for interrupted approval continuations.

A retry never reuses the original approval continuation. It consumes a separately
recorded RETRY_AUTHORIZED recovery decision, requires the request to carry the same
fresh JKD-001 authority context, atomically consumes the recovery authorization, and
routes execution only through the Central Orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

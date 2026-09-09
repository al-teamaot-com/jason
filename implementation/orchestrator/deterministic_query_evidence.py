"""Deterministic-only fallback for universal query evidence materialization.

Providers participating in the universal query architecture are expected to expose
canonical semantic evidence through their governed adapter/projection contract.

This object deliberately does not guess where unknown evidence lives.
"""


from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeterministicOnlyEvidenceLocator:
    def locate(
        self,
        *,
        requested_facts,
        data,
    ):
        del requested_facts
        del data

        return ()

#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping


BASE_SCRIPT = Path(__file__).with_name("recover-datto-rmm-execution-staging.py")
SPEC = importlib.util.spec_from_file_location("datto_execution_recovery_base", BASE_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the approved Datto execution recovery base utility.")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

RecoveryError = BASE.RecoveryError


def normalize_policy(value: str) -> str:
    return BASE.normalize_policy(value)


def extract_existing_policy_text(response: Mapping[str, Any]) -> str:
    """Extract policy text from the response shapes observed or previously modeled.

    Jason's live OpenBao 2.6.1 deployment returned the ACL policy at
    ``data.policy``. Earlier source/tests modeled top-level ``policy`` and a
    compatibility ``data.rules`` shape. All non-empty policy representations
    present in a response must normalize to the same text, otherwise recovery
    fails closed.
    """

    candidates: list[str] = []

    top_level_policy = response.get("policy")
    if isinstance(top_level_policy, str) and top_level_policy:
        candidates.append(top_level_policy)

    data = response.get("data")
    if isinstance(data, Mapping):
        nested_policy = data.get("policy")
        if isinstance(nested_policy, str) and nested_policy:
            candidates.append(nested_policy)

        nested_rules = data.get("rules")
        if isinstance(nested_rules, str) and nested_rules:
            candidates.append(nested_rules)

    if not candidates:
        raise RecoveryError("Existing Datto execution policy rules were unavailable.")

    normalized = {normalize_policy(value) for value in candidates}
    if len(normalized) != 1:
        raise RecoveryError("Existing Datto execution policy response was inconsistent.")

    return candidates[0]


# The base main() resolves this function through its module globals, so replace
# only the proven parser defect while retaining the already-reviewed recovery
# transaction, CAS behavior, credential-isolation checks, and rollback hygiene.
BASE.extract_existing_policy_text = extract_existing_policy_text


def main() -> int:
    return BASE.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as error:
        print(f"ERROR: {error}", file=BASE.sys.stderr)
        raise SystemExit(1)

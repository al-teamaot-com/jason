from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence


PHASES = (
    "install",
    "initialize_state",
    "start_candidate",
    "verify_manifest_identity",
    "verify_ready",
    "verify_configuration",
    "verify_governance",
    "verify_isolation",
    "verify_provider_connectivity",
    "exercise_governed_workflow",
    "upgrade",
    "verify_upgraded_identity_health",
    "rollback",
    "create_full_recovery_export",
    "destroy_recreate_restore",
    "verify_restored_ready_equivalence",
    "repeat_clean_environment",
)


class ZeroToOperationalError(ValueError):
    pass


class AcceptanceExecutor(Protocol):
    def execute_phase(
        self,
        phase: str,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class PhaseReceipt:
    sequence: int
    phase: str
    status: str
    evidence_sha256: str | None
    summary: str


@dataclass(frozen=True, slots=True)
class AcceptanceReceipt:
    schema_version: str
    scenario_id: str
    mode: str
    status: str
    deployability_proven: bool
    production_authorized: bool
    phases: tuple[PhaseReceipt, ...]
    receipt_sha256: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _evidence_for_hash(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    # Evidence contracts must never carry raw secrets. Refuse obvious secret-value keys
    # rather than trusting callers to remember this at every phase.
    forbidden_fragments = (
        "password",
        "secret_value",
        "root_token",
        "unseal_key",
        "private_key",
        "access_token",
    )

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in forbidden_fragments):
                    raise ZeroToOperationalError(
                        f"acceptance evidence contains prohibited secret-bearing key at {path}/{key}"
                    )
                walk(child, path + "/" + str(key))
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, path + "/" + str(index))

    walk(evidence, "")
    return evidence


def run_zero_to_operational(
    *,
    scenario_id: str,
    mode: str,
    executor: AcceptanceExecutor,
    initial_context: Mapping[str, Any] | None = None,
) -> AcceptanceReceipt:
    scenario = scenario_id.strip()
    if not scenario:
        raise ZeroToOperationalError("scenario_id must be non-empty")
    if mode not in {"synthetic", "host"}:
        raise ZeroToOperationalError("mode must be synthetic or host")

    context: dict[str, Any] = dict(initial_context or {})
    context["scenario_id"] = scenario
    context["mode"] = mode
    context["production_authorized"] = False

    receipts: list[PhaseReceipt] = []
    failed = False

    for sequence, phase in enumerate(PHASES, start=1):
        if failed:
            receipts.append(
                PhaseReceipt(
                    sequence=sequence,
                    phase=phase,
                    status="SKIPPED",
                    evidence_sha256=None,
                    summary="Skipped after earlier acceptance failure.",
                )
            )
            continue

        try:
            raw = executor.execute_phase(phase, dict(context))
        except Exception as exc:
            receipts.append(
                PhaseReceipt(
                    sequence=sequence,
                    phase=phase,
                    status="FAIL",
                    evidence_sha256=_hash(
                        {"phase": phase, "error_type": type(exc).__name__}
                    ),
                    summary=f"{type(exc).__name__}: {exc}",
                )
            )
            failed = True
            continue

        try:
            if not isinstance(raw, Mapping):
                raise ZeroToOperationalError(
                    f"phase {phase} did not return an evidence object"
                )
            evidence = dict(_evidence_for_hash(raw))
            phase_status = str(evidence.pop("status", "PASS")).upper()
            if phase_status not in {"PASS", "FAIL"}:
                raise ZeroToOperationalError(
                    f"phase {phase} returned unsupported status {phase_status}"
                )
            summary = str(
                evidence.pop(
                    "summary",
                    "Phase completed." if phase_status == "PASS" else "Phase failed.",
                )
            )
            update = evidence.pop("context_update", {})
            if not isinstance(update, Mapping):
                raise ZeroToOperationalError(
                    f"phase {phase} context_update must be an object"
                )
            if "production_authorized" in update:
                raise ZeroToOperationalError(
                    "acceptance executor may not change production authorization"
                )
            context.update(dict(update))
            evidence_sha256 = _hash(
                {
                    "phase": phase,
                    "evidence": evidence,
                    "context_update": dict(update),
                }
            )
        except Exception as exc:
            receipts.append(
                PhaseReceipt(
                    sequence=sequence,
                    phase=phase,
                    status="FAIL",
                    evidence_sha256=_hash(
                        {"phase": phase, "error_type": type(exc).__name__}
                    ),
                    summary=f"{type(exc).__name__}: {exc}",
                )
            )
            failed = True
            continue

        receipts.append(
            PhaseReceipt(
                sequence=sequence,
                phase=phase,
                status=phase_status,
                evidence_sha256=evidence_sha256,
                summary=summary,
            )
        )
        if phase_status == "FAIL":
            failed = True

    overall = "FAIL" if failed else "PASS"
    deployability_proven = overall == "PASS" and mode == "host"
    material = {
        "schema_version": "1.0",
        "scenario_id": scenario,
        "mode": mode,
        "status": overall,
        "deployability_proven": deployability_proven,
        "production_authorized": False,
        "phases": [asdict(item) for item in receipts],
    }
    return AcceptanceReceipt(
        schema_version="1.0",
        scenario_id=scenario,
        mode=mode,
        status=overall,
        deployability_proven=deployability_proven,
        production_authorized=False,
        phases=tuple(receipts),
        receipt_sha256=_hash(material),
    )


def receipt_to_json(receipt: AcceptanceReceipt) -> str:
    return json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n"

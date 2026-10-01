"""Validated, canonical JSON playbook document model.

JSON playbooks describe operational procedure only.  They never create authority;
all capability execution remains subject to Jason identity, policy, approval and
Central Orchestrator enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence


_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_STEP_TYPES = frozenset({
    "diagnostic",
    "decision",
    "remediation",
    "verification",
    "wait",
    "document",
    "human_review",
    "complete",
    "escalate",
})
_TERMINAL_TYPES = frozenset({"human_review", "complete", "escalate"})
_APPROVAL_CLASSES = frozenset({
    "read_only",
    "non_destructive",
    "modifying",
    "disruptive",
})
_FORBIDDEN_STEP_KEYS = frozenset({
    "shell",
    "bash",
    "powershell",
    "script",
    "raw_command",
    "provider_url",
    "direct_provider_access",
})


class PlaybookValidationError(ValueError):
    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(str(item) for item in errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True, slots=True)
class PlaybookDocument:
    playbook_id: str
    name: str
    version: str
    lifecycle: str
    target_type: str
    entry_step: str
    capabilities: tuple[str, ...]
    fingerprint: str
    canonical_json: str
    payload: Mapping[str, Any]

    @property
    def autonomy_activation(self) -> str:
        autonomy = self.payload.get("autonomy")
        if not isinstance(autonomy, Mapping):
            return "disabled"
        return str(autonomy.get("activation") or "disabled").strip().casefold()


def canonical_playbook_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def validate_playbook_document(
    raw: Any,
    *,
    known_capabilities: set[str] | frozenset[str] | None = None,
) -> PlaybookDocument:
    errors: list[str] = []
    if not isinstance(raw, Mapping):
        raise PlaybookValidationError(("PLAYBOOK_JSON_OBJECT_REQUIRED",))

    try:
        json.dumps(raw, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise PlaybookValidationError(("PLAYBOOK_JSON_SERIALIZABLE_REQUIRED",))

    schema_version = raw.get("schema_version")
    if schema_version != 1:
        errors.append("PLAYBOOK_SCHEMA_VERSION_UNSUPPORTED")

    playbook = raw.get("playbook")
    if not isinstance(playbook, Mapping):
        errors.append("PLAYBOOK_METADATA_REQUIRED")
        playbook = {}

    playbook_id = str(playbook.get("id") or "").strip()
    name = str(playbook.get("name") or "").strip()
    version = str(playbook.get("version") or "").strip()
    lifecycle = str(playbook.get("lifecycle") or "").strip().casefold()
    target_type = str(playbook.get("target_type") or "").strip().casefold()

    if not _ID_RE.fullmatch(playbook_id):
        errors.append("PLAYBOOK_ID_INVALID")
    if not name:
        errors.append("PLAYBOOK_NAME_REQUIRED")
    if not _SEMVER_RE.fullmatch(version):
        errors.append("PLAYBOOK_VERSION_INVALID")
    if lifecycle not in {"draft", "pilot", "production"}:
        errors.append("PLAYBOOK_LIFECYCLE_INVALID")
    if target_type not in {
        "ticket", "endpoint", "user", "site", "service", "provider_object"
    }:
        errors.append("PLAYBOOK_TARGET_TYPE_INVALID")

    state_model = raw.get("state_model")
    if not isinstance(state_model, Mapping):
        errors.append("PLAYBOOK_STATE_MODEL_REQUIRED")
        state_model = {}
    entry_step = str(state_model.get("entry_step") or "").strip()
    if not _STEP_ID_RE.fullmatch(entry_step):
        errors.append("PLAYBOOK_ENTRY_STEP_INVALID")

    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("PLAYBOOK_STEPS_REQUIRED")
        steps = []
    if len(steps) > 200:
        errors.append("PLAYBOOK_STEP_LIMIT_EXCEEDED")

    by_id: dict[str, Mapping[str, Any]] = {}
    referenced_capabilities: set[str] = set()
    edges: dict[str, set[str]] = {}

    for index, raw_step in enumerate(steps):
        prefix = f"step[{index}]"
        if not isinstance(raw_step, Mapping):
            errors.append(f"{prefix}:STEP_OBJECT_REQUIRED")
            continue

        forbidden = sorted(_FORBIDDEN_STEP_KEYS.intersection(raw_step.keys()))
        if forbidden:
            errors.append(f"{prefix}:INLINE_EXECUTION_FORBIDDEN:{','.join(forbidden)}")

        step_id = str(raw_step.get("id") or "").strip()
        step_type = str(raw_step.get("type") or "").strip().casefold()
        if not _STEP_ID_RE.fullmatch(step_id):
            errors.append(f"{prefix}:STEP_ID_INVALID")
            continue
        if step_id in by_id:
            errors.append(f"{prefix}:STEP_ID_DUPLICATE:{step_id}")
            continue
        by_id[step_id] = raw_step
        edges.setdefault(step_id, set())

        if step_type not in _STEP_TYPES:
            errors.append(f"{step_id}:STEP_TYPE_INVALID")
            continue

        capability = str(raw_step.get("capability") or "").strip()
        if capability:
            if not _CAPABILITY_RE.fullmatch(capability) or any(
                token in capability for token in ("*", "?", "[", "]")
            ):
                errors.append(f"{step_id}:CAPABILITY_INVALID")
            else:
                referenced_capabilities.add(capability)
                if known_capabilities is not None and capability not in known_capabilities:
                    errors.append(f"{step_id}:CAPABILITY_NOT_REGISTERED:{capability}")

        if step_type in {"diagnostic", "remediation", "verification", "document"}:
            if not capability:
                errors.append(f"{step_id}:CAPABILITY_REQUIRED")

        arguments = raw_step.get("arguments", {})
        if not isinstance(arguments, Mapping):
            errors.append(f"{step_id}:ARGUMENTS_OBJECT_REQUIRED")

        retry = raw_step.get("retry")
        if retry is not None:
            if not isinstance(retry, Mapping):
                errors.append(f"{step_id}:RETRY_OBJECT_REQUIRED")
            else:
                attempts = retry.get("max_attempts", 1)
                if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 10:
                    errors.append(f"{step_id}:RETRY_BOUND_INVALID")

        if step_type == "remediation":
            approval = str(raw_step.get("approval_classification") or "").strip()
            if approval not in _APPROVAL_CLASSES:
                errors.append(f"{step_id}:APPROVAL_CLASSIFICATION_REQUIRED")
            if approval == "disruptive" and raw_step.get("approval_required") is not True:
                errors.append(f"{step_id}:DISRUPTIVE_APPROVAL_REQUIRED")
            verification_step = str(raw_step.get("verification_step") or "").strip()
            if not verification_step:
                errors.append(f"{step_id}:VERIFICATION_STEP_REQUIRED")
            else:
                edges[step_id].add(verification_step)

        if step_type == "decision":
            branches = raw_step.get("branches")
            if not isinstance(branches, list) or not branches:
                errors.append(f"{step_id}:DECISION_BRANCHES_REQUIRED")
            else:
                for branch_index, branch in enumerate(branches):
                    if not isinstance(branch, Mapping):
                        errors.append(f"{step_id}:BRANCH_OBJECT_REQUIRED:{branch_index}")
                        continue
                    condition = branch.get("when")
                    target = str(branch.get("next") or "").strip()
                    if not isinstance(condition, Mapping):
                        errors.append(f"{step_id}:BRANCH_CONDITION_REQUIRED:{branch_index}")
                    else:
                        operator = str(condition.get("operator") or "").strip().casefold()
                        fact = str(condition.get("fact") or "").strip()
                        if not fact or operator not in {
                            "eq", "ne", "in", "not_in", "exists", "truthy", "falsy"
                        }:
                            errors.append(f"{step_id}:BRANCH_CONDITION_INVALID:{branch_index}")
                    if not target:
                        errors.append(f"{step_id}:BRANCH_TARGET_REQUIRED:{branch_index}")
                    else:
                        edges[step_id].add(target)
            default_target = str(raw_step.get("default") or "").strip()
            if not default_target:
                errors.append(f"{step_id}:DECISION_DEFAULT_REQUIRED")
            else:
                edges[step_id].add(default_target)
        elif step_type == "wait":
            resume = str(raw_step.get("resume") or "").strip()
            if not resume:
                errors.append(f"{step_id}:WAIT_RESUME_REQUIRED")
            else:
                edges[step_id].add(resume)
            seconds = raw_step.get("seconds")
            wake_on = str(raw_step.get("wake_on") or "").strip()
            if (seconds is None) == (not wake_on):
                errors.append(f"{step_id}:WAIT_TRIGGER_EXACTLY_ONE_REQUIRED")
            if seconds is not None and (
                isinstance(seconds, bool) or not isinstance(seconds, int) or not 60 <= seconds <= 2592000
            ):
                errors.append(f"{step_id}:WAIT_SECONDS_INVALID")
        elif step_type not in _TERMINAL_TYPES:
            target = str(raw_step.get("next") or "").strip()
            if not target and step_type != "remediation":
                errors.append(f"{step_id}:NEXT_STEP_REQUIRED")
            elif target:
                edges[step_id].add(target)

    if entry_step and entry_step not in by_id:
        errors.append("PLAYBOOK_ENTRY_STEP_NOT_FOUND")

    for source, targets in edges.items():
        for target in targets:
            if target not in by_id:
                errors.append(f"{source}:TARGET_NOT_FOUND:{target}")

    if not errors and entry_step:
        reachable: set[str] = set()
        visiting: set[str] = set()

        def walk(node: str) -> None:
            if node in visiting:
                raise PlaybookValidationError((f"PLAYBOOK_GRAPH_CYCLE_FORBIDDEN:{node}",))
            if node in reachable:
                return
            visiting.add(node)
            reachable.add(node)
            for child in edges.get(node, ()):
                walk(child)
            visiting.remove(node)

        walk(entry_step)
        unreachable = sorted(set(by_id) - reachable)
        if unreachable:
            errors.append("PLAYBOOK_UNREACHABLE_STEPS:" + ",".join(unreachable))

    verification = raw.get("verification")
    if not isinstance(verification, Mapping):
        errors.append("PLAYBOOK_VERIFICATION_REQUIRED")
    else:
        if not str(verification.get("authoritative_source") or "").strip():
            errors.append("PLAYBOOK_AUTHORITATIVE_VERIFICATION_SOURCE_REQUIRED")
        if not str(verification.get("success_condition") or "").strip():
            errors.append("PLAYBOOK_VERIFICATION_SUCCESS_CONDITION_REQUIRED")

    completion = raw.get("completion")
    if not isinstance(completion, Mapping):
        errors.append("PLAYBOOK_COMPLETION_REQUIRED")
    elif not str(completion.get("terminal_disposition") or "").strip():
        errors.append("PLAYBOOK_TERMINAL_DISPOSITION_REQUIRED")

    autonomy = raw.get("autonomy", {})
    if not isinstance(autonomy, Mapping):
        errors.append("PLAYBOOK_AUTONOMY_OBJECT_REQUIRED")
        autonomy = {}
    activation = str(autonomy.get("activation") or "disabled").strip().casefold()
    if activation not in {"disabled", "shadow", "autonomous", "suspended"}:
        errors.append("PLAYBOOK_AUTONOMY_ACTIVATION_INVALID")
    allowed = autonomy.get("allowed_capabilities", [])
    if not isinstance(allowed, list):
        errors.append("PLAYBOOK_AUTONOMY_CAPABILITIES_ARRAY_REQUIRED")
        allowed = []
    normalized_allowed: list[str] = []
    for item in allowed:
        value = str(item or "").strip()
        if (
            not _CAPABILITY_RE.fullmatch(value)
            or any(token in value for token in ("*", "?", "[", "]"))
        ):
            errors.append("PLAYBOOK_AUTONOMY_EXACT_CAPABILITY_REQUIRED")
        else:
            normalized_allowed.append(value)
    if len(set(normalized_allowed)) != len(normalized_allowed):
        errors.append("PLAYBOOK_AUTONOMY_CAPABILITY_DUPLICATE")
    if activation == "autonomous" and not normalized_allowed:
        errors.append("PLAYBOOK_AUTONOMY_CAPABILITIES_REQUIRED")
    undeclared = sorted(referenced_capabilities - set(normalized_allowed))
    if activation == "autonomous" and undeclared:
        errors.append("PLAYBOOK_AUTONOMY_CAPABILITY_SCOPE_MISSING:" + ",".join(undeclared))

    if errors:
        raise PlaybookValidationError(tuple(errors))

    canonical = canonical_playbook_json(raw)
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
    return PlaybookDocument(
        playbook_id=playbook_id,
        name=name,
        version=version,
        lifecycle=lifecycle,
        target_type=target_type,
        entry_step=entry_step,
        capabilities=tuple(sorted(referenced_capabilities)),
        fingerprint=fingerprint,
        canonical_json=canonical,
        payload=dict(raw),
    )

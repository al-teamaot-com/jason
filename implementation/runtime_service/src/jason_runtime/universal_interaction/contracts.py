"""Jason universal interaction v1: a declarative presentation contract.

No Microsoft identity, approval authority, provider invocation or execution
capability is granted by this object. Calling workflows own the questions;
existing JKD, audience and ApprovalRequest services own who can answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping
import re

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


def _token(value: str, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("invalid " + label)


class InteractionKind(str, Enum):
    NOTICE = "notice"
    PROGRESS = "progress"
    QUESTIONNAIRE = "questionnaire"
    APPROVAL = "approval"
    ACKNOWLEDGEMENT = "acknowledgement"


class VisualIntent(str, Enum):
    INFORMATION = "information"
    ACTION_REQUIRED = "action_required"
    CAUTION = "caution"
    CRITICAL = "critical"
    SUCCESS = "success"


class FieldType(str, Enum):
    TEXT = "text"
    PARAGRAPH = "paragraph"
    NUMBER = "number"
    CURRENCY = "currency"
    BOOLEAN = "boolean"
    SELECT = "select"
    DATE = "date"


class ActionType(str, Enum):
    SUBMIT = "submit"
    APPROVE = "approve"
    DENY = "deny"
    ACKNOWLEDGE = "acknowledge"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Option:
    value: str
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not 1 <= len(self.value) <= 120:
            raise ValueError("invalid option value")
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 160:
            raise ValueError("invalid option label")


@dataclass(frozen=True)
class Condition:
    depends_on: str
    equals: str | bool

    def __post_init__(self) -> None:
        _token(self.depends_on, "condition")
        if type(self.equals) not in (str, bool):
            raise ValueError("conditional value must be scalar")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    field_type: FieldType
    required: bool = False
    options: tuple[Option, ...] = ()
    currency: str | None = None
    minimum: str | None = None
    maximum: str | None = None
    max_length: int = 1024
    show_when: Condition | None = None

    def __post_init__(self) -> None:
        _token(self.key, "field key")
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 160:
            raise ValueError("invalid field label")
        if not isinstance(self.field_type, FieldType) or type(self.required) is not bool:
            raise ValueError("invalid field configuration")
        if self.field_type is FieldType.SELECT:
            if not self.options or len({o.value for o in self.options}) != len(self.options):
                raise ValueError("select needs unique options")
        elif self.options:
            raise ValueError("options only valid for select")
        if self.field_type is FieldType.CURRENCY:
            if not isinstance(self.currency, str) or re.fullmatch(r"[A-Z]{3}", self.currency) is None:
                raise ValueError("currency field requires ISO code")
        elif self.currency is not None:
            raise ValueError("currency only valid for currency field")
        if type(self.max_length) is not int or not 1 <= self.max_length <= 4096:
            raise ValueError("invalid max length")
        if self.minimum is not None or self.maximum is not None:
            if self.field_type not in (FieldType.CURRENCY, FieldType.NUMBER):
                raise ValueError("bounds apply only to numeric fields")
            try:
                low = Decimal(self.minimum) if self.minimum is not None else None
                high = Decimal(self.maximum) if self.maximum is not None else None
            except (InvalidOperation, TypeError) as exc:
                raise ValueError("numeric bound is invalid") from exc
            if any(not x.is_finite() for x in (low, high) if x is not None):
                raise ValueError("nonfinite bound")
            if low is not None and high is not None and low > high:
                raise ValueError("minimum exceeds maximum")


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    intent: ActionType

    def __post_init__(self) -> None:
        _token(self.key, "action")
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 100:
            raise ValueError("invalid action label")
        if not isinstance(self.intent, ActionType):
            raise ValueError("invalid action intent")


@dataclass(frozen=True)
class Fact:
    label: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 120:
            raise ValueError("invalid fact label")
        if not isinstance(self.value, str) or len(self.value) > 1500:
            raise ValueError("invalid fact value")


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    workflow: str
    correlation_id: str
    organization_id: str
    requester_identity_id: str
    kind: InteractionKind
    title: str
    summary: str
    visual_intent: VisualIntent
    facts: tuple[Fact, ...] = ()
    fields: tuple[Field, ...] = ()
    actions: tuple[Action, ...] = ()
    approval_id: str | None = None
    expires_at: datetime | None = None
    client_id: str | None = None
    contract_version: str = "1.0"

    def __post_init__(self) -> None:
        for label in ("interaction_id", "workflow", "correlation_id",
                      "organization_id", "requester_identity_id"):
            _token(getattr(self, label), label)
        if self.client_id is not None:
            _token(self.client_id, "client")
        if self.contract_version != "1.0":
            raise ValueError("unsupported contract version")
        if not isinstance(self.kind, InteractionKind) or not isinstance(self.visual_intent, VisualIntent):
            raise ValueError("invalid kind or presentation")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= 180:
            raise ValueError("invalid title")
        if not isinstance(self.summary, str) or not 1 <= len(self.summary) <= 5000:
            raise ValueError("invalid summary")
        if len(self.facts) > 30 or len(self.fields) > 40 or len(self.actions) > 8:
            raise ValueError("interaction exceeds complexity limit")
        field_keys = [f.key for f in self.fields]
        action_keys = [a.key for a in self.actions]
        if len(field_keys) != len(set(field_keys)) or len(action_keys) != len(set(action_keys)):
            raise ValueError("duplicate field or action")
        for index, field in enumerate(self.fields):
            if field.show_when is not None and field.show_when.depends_on not in field_keys[:index]:
                raise ValueError("condition must reference an earlier field")
        approval_intents = {ActionType.APPROVE, ActionType.DENY}
        if self.kind is InteractionKind.APPROVAL:
            if not self.approval_id or self.expires_at is None:
                raise ValueError("approval requires existing request and expiry")
            _token(self.approval_id, "persisted approval")
            if self.fields or {a.intent for a in self.actions} != approval_intents:
                raise ValueError("approval cannot carry form fields or missing actions")
        elif self.approval_id is not None or any(a.intent in approval_intents for a in self.actions):
            raise ValueError("only existing approvals may request approve/deny")
        if self.kind is InteractionKind.QUESTIONNAIRE:
            if not self.fields or not any(a.intent is ActionType.SUBMIT for a in self.actions):
                raise ValueError("questionnaire needs fields and submit")
        elif self.fields:
            raise ValueError("forms only allowed in questionnaire")
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValueError("expiry requires timezone")
        if self.kind in (InteractionKind.NOTICE, InteractionKind.PROGRESS) and self.actions:
            raise ValueError("status messages are non-actionable")


def validate_answers(spec: Interaction, answers: Mapping[str, Any]) -> dict[str, Any]:
    """Only generic form syntax; procurement/business limits stay with caller."""
    if spec.kind is not InteractionKind.QUESTIONNAIRE or not isinstance(answers, Mapping):
        raise ValueError("questionnaire answers required")
    allowed = {f.key for f in spec.fields}
    if any(key not in allowed for key in answers):
        raise ValueError("unknown answer key")
    validated: dict[str, Any] = {}
    for field in spec.fields:
        if field.show_when is not None and (
            answers.get(field.show_when.depends_on) != field.show_when.equals
        ):
            if field.key in answers:
                raise ValueError("hidden conditional field submitted")
            continue
        value = answers.get(field.key)
        if value is None or value == "":
            if field.required:
                raise ValueError("required field missing: " + field.key)
            continue
        if field.field_type is FieldType.BOOLEAN:
            if type(value) is not bool:
                raise ValueError("invalid boolean answer")
        elif field.field_type in (FieldType.NUMBER, FieldType.CURRENCY):
            if type(value) not in (int, float, str):
                raise ValueError("invalid numeric answer")
            try:
                number = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError("invalid numeric answer") from exc
            if not number.is_finite():
                raise ValueError("nonfinite numeric answer")
            if field.minimum is not None and number < Decimal(field.minimum):
                raise ValueError("numeric value below minimum")
            if field.maximum is not None and number > Decimal(field.maximum):
                raise ValueError("numeric value above maximum")
            if field.field_type is FieldType.CURRENCY:
                value = str(number)  # no binary float conversion for money
        elif field.field_type is FieldType.SELECT:
            if type(value) is not str or value not in {o.value for o in field.options}:
                raise ValueError("invalid selection")
        elif field.field_type is FieldType.DATE:
            if type(value) is not str:
                raise ValueError("invalid date")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("invalid date") from exc
        elif type(value) is not str or len(value) > field.max_length:
            raise ValueError("invalid text")
        validated[field.key] = value
    return validated

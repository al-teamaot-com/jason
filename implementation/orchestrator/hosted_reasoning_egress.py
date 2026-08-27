"""Local data-egress classification for hosted reasoning.

This boundary runs before any hosted reasoning provider is contacted. It is deliberately
provider-neutral and deterministic. A hosted model must never be used to decide whether
the text may be sent to that hosted model.

The first policy is intentionally conservative. Clearly sensitive, regulated,
credential-bearing, or secret-oriented material is classified restricted and is not
eligible for hosted processing. Ordinary AOT operational conversation is classified
internal and may be considered by Jason's Execution Policy Engine.

Classification is a policy input, not provider authority.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from kernel.execution_policy import DataHandlingPolicy

from .evidence_sanitization import is_sensitive_value


_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_PAYMENT_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

_RESTRICTED_TERMS = (
    re.compile(
        r"\b("
        r"password|passwd|passphrase|"
        r"api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
        r"client[ _-]?secret|private[ _-]?key|recovery[ _-]?key|"
        r"bearer[ _-]?token"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b("
        r"social security|ssn|"
        r"credit card|card number|cvv|cvc|"
        r"bank account|routing number"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b("
        r"phi|protected health information|"
        r"patient|medical record|medical history|diagnosis|"
        r"prescription|treatment record"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b("
        r"cui|controlled unclassified information|"
        r"fci|federal contract information|"
        r"itar|export controlled"
        r")\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class HostedReasoningEgressDecision:
    classification: str
    hosted_processing_allowed: bool
    reason_codes: tuple[str, ...]
    redaction_profile: str | None = None

    @property
    def data_handling(self) -> DataHandlingPolicy:
        return DataHandlingPolicy(
            classification=self.classification,
            hosted_processing_allowed=self.hosted_processing_allowed,
            redaction_profile=self.redaction_profile,
            retention_allowed=False,
        )


class HostedReasoningEgressClassifier:
    """Classify hosted-model eligibility locally and fail closed on sensitive content."""

    def classify(self, *, user_payload: str) -> HostedReasoningEgressDecision:
        if not isinstance(user_payload, str) or not user_payload.strip():
            return self._deny("empty_or_invalid_payload")

        scalar_values = tuple(_scalar_strings(user_payload))

        for value in scalar_values:
            if is_sensitive_value(value):
                return self._deny("secret_shaped_value")

            if _SSN.search(value):
                return self._deny("personal_identifier")

            if _looks_like_payment_card(value):
                return self._deny("payment_card_data")

            for pattern in _RESTRICTED_TERMS:
                if pattern.search(value):
                    return self._deny("restricted_content_indicator")

        return HostedReasoningEgressDecision(
            classification="internal",
            hosted_processing_allowed=True,
            reason_codes=("ordinary_internal_conversation",),
            redaction_profile="hosted-conversation-minimum",
        )

    @staticmethod
    def _deny(reason: str) -> HostedReasoningEgressDecision:
        return HostedReasoningEgressDecision(
            classification="restricted",
            hosted_processing_allowed=False,
            reason_codes=(reason,),
            redaction_profile="hosted-conversation-deny",
        )


def _scalar_strings(raw: str):
    """Inspect structured kernel payloads without requiring them to be JSON."""

    yield raw

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    yield from _walk(parsed)


def _walk(value: Any):
    if isinstance(value, str):
        yield value
        return

    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk(item)
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _looks_like_payment_card(value: str) -> bool:
    for match in _PAYMENT_CARD.finditer(value):
        digits = "".join(char for char in match.group(0) if char.isdigit())

        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return True

    return False


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2

    for index, char in enumerate(digits):
        number = int(char)

        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9

        total += number

    return total % 10 == 0

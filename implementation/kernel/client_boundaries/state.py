from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Mapping

from kernel.client_boundaries.contracts import (
    OnboardingTransaction,
    SignedOnboardingState,
    TransactionStatus,
)
from kernel.client_boundaries.repositories import (
    InMemoryOnboardingTransactionRepository,
)


class OnboardingStateError(RuntimeError):
    """Safe onboarding-state validation failure."""


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode(
        "ascii"
    )


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, UnicodeEncodeError) as error:
        raise OnboardingStateError(
            "Onboarding state is malformed."
        ) from error


class OnboardingStateService:
    def __init__(
        self,
        *,
        signing_key: bytes,
        transactions: InMemoryOnboardingTransactionRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError(
                "Onboarding signing key must be at least 32 bytes."
            )

        self._signing_key = signing_key
        self._transactions = transactions
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

    def issue(
        self,
        transaction: OnboardingTransaction,
    ) -> SignedOnboardingState:
        if transaction.status is not TransactionStatus.PENDING:
            raise OnboardingStateError(
                "Only pending transactions can issue state."
            )

        now = self._require_aware(self._clock())

        if transaction.expires_at <= now:
            raise OnboardingStateError(
                "Onboarding transaction has expired."
            )

        payload = {
            "transaction_id": transaction.id,
            "client_id": transaction.client_id,
            "provider": transaction.provider,
            "profile": transaction.profile,
            "application_id": transaction.application_id,
            "nonce": transaction.nonce,
            "expires_at": transaction.expires_at.isoformat(),
        }

        payload_bytes = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        encoded_payload = _encode_base64url(payload_bytes)
        signature = hmac.new(
            self._signing_key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()

        return SignedOnboardingState(
            value=(
                f"{encoded_payload}."
                f"{_encode_base64url(signature)}"
            ),
            transaction_id=transaction.id,
            expires_at=transaction.expires_at,
        )

    def consume(
        self,
        state: str,
    ) -> OnboardingTransaction:
        payload = self._verify_and_parse(state)

        transaction_id = self._required_string(
            payload,
            "transaction_id",
        )

        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise OnboardingStateError(
                "Onboarding transaction was not found."
            )

        now = self._require_aware(self._clock())

        if transaction.status is not TransactionStatus.PENDING:
            raise OnboardingStateError(
                "Onboarding transaction is no longer pending."
            )

        if transaction.expires_at <= now:
            expired = replace(
                transaction,
                status=TransactionStatus.EXPIRED,
                last_error_code="ONBOARDING_TRANSACTION_EXPIRED",
            )
            self._transactions.replace(expired)

            raise OnboardingStateError(
                "Onboarding transaction has expired."
            )

        expected_values = {
            "client_id": transaction.client_id,
            "provider": transaction.provider,
            "profile": transaction.profile,
            "application_id": transaction.application_id,
            "nonce": transaction.nonce,
            "expires_at": transaction.expires_at.isoformat(),
        }

        for field_name, expected in expected_values.items():
            actual = self._required_string(
                payload,
                field_name,
            )

            if not hmac.compare_digest(actual, expected):
                raise OnboardingStateError(
                    "Onboarding state does not match "
                    "the stored transaction."
                )

        completed = replace(
            transaction,
            status=TransactionStatus.COMPLETED,
            completed_at=now,
        )
        self._transactions.replace(completed)

        return completed

    def _verify_and_parse(
        self,
        state: str,
    ) -> Mapping[str, object]:
        try:
            encoded_payload, encoded_signature = state.split(
                ".",
                maxsplit=1,
            )
        except ValueError as error:
            raise OnboardingStateError(
                "Onboarding state is malformed."
            ) from error

        expected_signature = hmac.new(
            self._signing_key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()

        supplied_signature = _decode_base64url(
            encoded_signature
        )

        if not hmac.compare_digest(
            expected_signature,
            supplied_signature,
        ):
            raise OnboardingStateError(
                "Onboarding state signature is invalid."
            )

        try:
            parsed = json.loads(
                _decode_base64url(encoded_payload).decode(
                    "utf-8"
                )
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise OnboardingStateError(
                "Onboarding state payload is invalid."
            ) from error

        if not isinstance(parsed, Mapping):
            raise OnboardingStateError(
                "Onboarding state payload is invalid."
            )

        return parsed

    @staticmethod
    def _required_string(
        payload: Mapping[str, object],
        field_name: str,
    ) -> str:
        value = payload.get(field_name)

        if not isinstance(value, str) or not value:
            raise OnboardingStateError(
                f"Onboarding state is missing {field_name}."
            )

        return value

    @staticmethod
    def _require_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "Clock must return a timezone-aware datetime."
            )

        return value

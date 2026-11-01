"""Deterministic invoice math; source documents never grant purchasing authority.

Only reads already-normalized untrusted invoice facts. Produces evidence for
review; no provider access or mutation, and no attempt to auto-correct a source.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")


class InvoiceFidelityError(ValueError):
    """Source invoice and proposed purchase cannot be reconciled safely."""


def _amount(value: Any, *, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise InvoiceFidelityError(f"{field} is missing or invalid")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvoiceFidelityError(f"{field} is not a valid monetary amount") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99"):
        raise InvoiceFidelityError(f"{field} must be a finite, nonnegative amount")
    try:
        cents = amount.quantize(CENT)
    except InvalidOperation as exc:
        raise InvoiceFidelityError(f"{field} is outside supported monetary precision") from exc
    if cents != amount:
        raise InvoiceFidelityError(f"{field} must be an exact amount in cents")
    return cents


def _optional_amount(source: Mapping[str, Any], field: str) -> Decimal:
    value = source.get(field)
    return Decimal("0.00") if value in (None, "") else _amount(value, field=field)


def _quantity(raw: Any) -> int:
    if isinstance(raw, bool):
        raise InvoiceFidelityError("invoice quantity must be an integer")
    try:
        qty = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise InvoiceFidelityError("invoice quantity must be an integer") from exc
    if str(raw).strip() != str(qty) or not 1 <= qty <= 1000:
        raise InvoiceFidelityError("invoice quantity must be an integer from 1 to 1000")
    return qty


def summarize_vendor_invoice(
    source: Mapping[str, Any],
    lines: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Reconcile a reported invoice total without changing the source evidence.

    An unavailable invoice total remains unavailable, not silently treated as
    zero or falsely reported as matching.
    """
    if str(source.get("source_kind") or "").strip().casefold() != "vendor_invoice":
        return {}
    total_raw = source.get("invoice_total")
    if total_raw in (None, ""):
        return {}
    if not lines or len(lines) > 100:
        raise InvoiceFidelityError("invoice must contain 1 to 100 source lines")
    items = Decimal("0.00")
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, Mapping):
            raise InvoiceFidelityError(f"invoice line {index} is invalid")
        unit = line.get("unit_cost")
        if unit is None:
            unit = line.get("price")
        items += _amount(unit, field=f"invoice line {index} unit cost") * _quantity(
            line.get("quantity", 1)
        )
    freight = _optional_amount(source, "freight")
    tax = _optional_amount(source, "tax")
    fees = _optional_amount(source, "fees")
    reported = _amount(total_raw, field="invoice total")
    calculated = items + freight + tax + fees
    delta = reported - calculated
    return {
        "status": "matched" if delta == 0 else "mismatch",
        "source_total": f"{reported:.2f}",
        "line_total": f"{items:.2f}",
        "calculated_total": f"{calculated:.2f}",
        "difference": f"{delta:.2f}",
    }


def validate_invoice_submission(
    source: Mapping[str, Any],
    *,
    quantity: int,
    freight: Decimal,
    tax: Decimal,
    fees: Decimal,
) -> None:
    """Fail before catalog/PO writes if an invoice draft undercounts its source."""
    proof = source.get("invoice_reconciliation")
    if not isinstance(proof, Mapping):
        return  # Legacy source without an asserted invoice total.
    if proof.get("status") != "matched":
        raise InvoiceFidelityError(
            "Source invoice total does not match lines, freight, tax and fees; "
            "Human Review is required before processing."
        )
    # Multiple lines are never silently condensed into a single PO item.
    lines = source.get("parts")
    if not isinstance(lines, list) or len(lines) != 1:
        raise InvoiceFidelityError(
            "Multi-line invoice requires a separately validated complete PO line plan."
        )
    original = lines[0]
    if not isinstance(original, Mapping) or quantity != _quantity(original.get("quantity", 1)):
        raise InvoiceFidelityError(
            "Selected quantity differs from source invoice; Human Review required."
        )
    for field, selected in (("freight", freight), ("tax", tax), ("fees", fees)):
        if selected != _optional_amount(source, field):
            raise InvoiceFidelityError(
                f"Selected {field} differs from source invoice; Human Review required."
            )
    original_cost = _amount(original.get("cost"), field="source invoice unit cost")
    approved_total = original_cost * quantity + freight + tax + fees
    if approved_total != _amount(proof.get("source_total"), field="invoice total"):
        raise InvoiceFidelityError(
            "Proposed PO does not equal verified invoice total; Human Review required."
        )

"""Deterministic first-pass playbook classification from queue evidence."""

from __future__ import annotations

from typing import Any, Mapping

from .autonomous_queue_worker import QueueCandidate
from .playbook_catalog import PlaybookCatalog, PlaybookCatalogEntry
from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore
from .playbook_matching import EligibilityGate, GateState, MatchState, PlaybookMatch, PlaybookMatcher


class CatalogPlaybookClassifier:
    """Nominate playbooks from explicit catalog triggers only.

    Ticket content is evidence. It can satisfy a catalog trigger but it cannot
    promote autonomy, add capabilities, or create governance authority.
    """

    def __init__(self, catalog: PlaybookCatalog, *, promotion_store: SQLitePlaybookAutonomyApprovalStore | None = None) -> None:
        self.catalog = catalog
        self.promotion_store = promotion_store

    def classify(self, candidate: QueueCandidate) -> PlaybookMatch:
        matches = [
            entry for entry in self.catalog.list_all()
            if entry.investigation_enabled and self._trigger_matches(entry, candidate.context)
        ]
        if not matches:
            return PlaybookMatch(
                playbook_id="none",
                state=MatchState.NOT_MATCHED,
                gates=(EligibilityGate("trigger", GateState.FAIL, "No catalog trigger matched"),),
                reasons=("No approved/shadow playbook trigger matched this ticket.",),
            )
        if len(matches) > 1:
            ids = tuple(sorted(entry.playbook_id for entry in matches))
            return PlaybookMatch(
                playbook_id="ambiguous",
                state=MatchState.CONFLICT_BLOCKED,
                gates=(EligibilityGate("trigger", GateState.FAIL, "Multiple playbook triggers matched", True),),
                reasons=("Multiple playbooks matched: " + ", ".join(ids),),
            )

        entry = matches[0]
        gates = [EligibilityGate("trigger", GateState.PASS)]
        for gate_name in entry.required_gates:
            if gate_name == "trigger":
                continue
            if gate_name == "identity":
                config_id = candidate.context.get("configurationItemID")
                state = GateState.PASS if self._positive_int(config_id) else GateState.UNKNOWN
                gates.append(EligibilityGate("identity", state, "Exact CI/device identity not yet proven" if state is GateState.UNKNOWN else "", True))
                continue
            if gate_name == "autonomy_approved":
                promoted = self._durably_promoted(entry)
                state = GateState.PASS if promoted else GateState.UNKNOWN
                gates.append(EligibilityGate(
                    "autonomy_approved",
                    state,
                    "Playbook lacks exact durable standing-autonomy promotion authority" if state is GateState.UNKNOWN else "",
                    True,
                ))
                continue
            gates.append(EligibilityGate(gate_name, GateState.UNKNOWN, f"Required gate not yet evaluated: {gate_name}"))

        # Every catalog entry needs the explicit autonomy gate before execution,
        # even if an older metadata record forgot to list it.
        if not any(gate.name == "autonomy_approved" for gate in gates):
            gates.append(EligibilityGate(
                "autonomy_approved",
                GateState.PASS if self._durably_promoted(entry) else GateState.UNKNOWN,
                "Playbook is not durably promoted to autonomous execution" if not self._durably_promoted(entry) else "",
                True,
            ))

        return PlaybookMatcher.evaluate(playbook_id=entry.playbook_id, gates=gates)

    def _durably_promoted(self, entry: PlaybookCatalogEntry) -> bool:
        if not entry.standing_authority_active:
            return False
        if self.promotion_store is None or not entry.autonomy_policy_id:
            return False
        return self.promotion_store.find_scope_approved(
            playbook_id=entry.playbook_id,
            playbook_version=entry.version,
            policy_id=entry.autonomy_policy_id,
            required_capabilities=entry.allowed_capabilities,
        ) is not None

    @staticmethod
    def _trigger_matches(entry: PlaybookCatalogEntry, ticket: Mapping[str, Any]) -> bool:
        title = str(ticket.get("title") or "").casefold()
        title_match = (
            any(fragment in title for fragment in entry.trigger_title_contains)
            if entry.trigger_title_contains
            else True
        )
        if not title_match:
            return False

        if entry.trigger_api_vendor_ids:
            raw = ticket.get("apiVendorID")
            try:
                vendor_id = int(raw)
            except (TypeError, ValueError):
                return False
            if vendor_id not in entry.trigger_api_vendor_ids:
                return False
        return bool(entry.trigger_title_contains or entry.trigger_api_vendor_ids)

    @staticmethod
    def _positive_int(value: Any) -> bool:
        if value is None or isinstance(value, bool):
            return False
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            return False

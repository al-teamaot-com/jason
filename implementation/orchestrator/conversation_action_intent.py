from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from kernel.capabilities import CapabilityDefinition, CapabilityRegistryService

from .teams_conversation_flow import BoundConversationPrincipal, ConversationIntent


class StructuredActionIntentReasoner(Protocol):
    """Interpret a human command using only registered provider-neutral capabilities."""

    def propose(
        self,
        *,
        text: str,
        organization_id: str,
        client_id: str | None,
        candidates: Sequence[CapabilityDefinition],
    ) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class GovernedActionConversationIntentResolver:
    """Resolve imperative conversation turns into registered governed capabilities.

    The reasoner may choose only from capabilities explicitly marked as conversational
    actions in capability metadata. Provider selection, credentials, authority, approval,
    and execution remain outside the reasoner. First-person targets are resolved from
    Jason-owned identity binding data rather than from transport-supplied addresses.
    """

    registry: CapabilityRegistryService
    reasoner: StructuredActionIntentReasoner

    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | None:
        candidates = tuple(
            item
            for item in self.registry.list_all()
            if str(item.metadata.get("conversation_action_enabled", "")).lower() == "true"
        )
        if not candidates:
            return None

        proposal = self.reasoner.propose(
            text=text,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            candidates=candidates,
        )
        if proposal is None:
            return None
        if not isinstance(proposal, Mapping):
            raise ValueError("action intent reasoner must return an object")

        capability_name = str(proposal.get("capability_name", "")).strip()
        by_name = {item.capability_name: item for item in candidates}
        capability = by_name.get(capability_name)
        if capability is None:
            raise PermissionError("action reasoner selected a capability outside governed candidates")

        raw_arguments = proposal.get("arguments", {})
        if not isinstance(raw_arguments, Mapping):
            raise ValueError("action intent arguments must be an object")
        arguments = dict(raw_arguments)

        allowed_keys = _metadata_csv(capability.metadata.get("conversation_argument_keys"))
        if not allowed_keys:
            raise ValueError("conversational action capability has no approved argument contract")
        unexpected = sorted(set(arguments) - allowed_keys)
        if unexpected:
            raise PermissionError(
                "action reasoner supplied arguments outside the governed contract: "
                + ", ".join(unexpected)
            )

        if proposal.get("self_target") is True:
            target_field = str(
                capability.metadata.get("conversation_self_target_field", "")
            ).strip()
            if not target_field or target_field not in allowed_keys:
                raise ValueError("capability does not define a governed self-target field")
            if principal.email_address is None:
                raise LookupError("bound Teams principal has no governed delivery address")
            if target_field in arguments:
                raise PermissionError("reasoner may not override a Jason-resolved self target")
            arguments[target_field] = [principal.email_address]

        defaults = {
            "subject": capability.metadata.get("conversation_default_subject"),
            "text_body": capability.metadata.get("conversation_default_text_body"),
        }
        for key, value in defaults.items():
            if key in allowed_keys and key not in arguments and value is not None and str(value).strip():
                arguments[key] = str(value)

        return ConversationIntent(
            capability_name=capability.capability_name,
            capability_version=capability.version,
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="execute",
            risk=capability.risk_level.value,
        )


def _metadata_csv(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(item).strip() for item in value if str(item).strip())
    raise ValueError("conversation capability metadata must be a string or sequence")


@dataclass(frozen=True, slots=True)
class ChainedConversationIntentResolver:
    """Try governed intent resolvers in order without merging or flattening intents."""

    resolvers: tuple[Any, ...]

    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | None:
        for resolver in self.resolvers:
            intent = resolver.resolve(text=text, principal=principal)
            if intent is not None:
                return intent
        return None

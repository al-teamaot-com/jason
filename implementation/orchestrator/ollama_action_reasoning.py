from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from kernel.capabilities import CapabilityDefinition

from .ollama_reasoning import OllamaStructuredJsonClient


@dataclass(frozen=True, slots=True)
class OllamaActionIntentReasoner:
    """Use local reasoning only to describe a requested registered action."""

    client: OllamaStructuredJsonClient

    def propose(
        self,
        *,
        text: str,
        organization_id: str,
        client_id: str | None,
        candidates: Sequence[CapabilityDefinition],
    ) -> Mapping[str, Any] | None:
        names = [item.capability_name for item in candidates]
        if not names:
            return None

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resolved": {"type": "boolean"},
                "capability_name": {"type": "string", "enum": names},
                "arguments": {"type": "object"},
                "self_target": {"type": "boolean"},
            },
            "required": ["resolved", "capability_name", "arguments", "self_target"],
        }
        candidate_metadata = [
            {
                "capability_name": item.capability_name,
                "display_name": item.display_name,
                "business_purpose": item.business_purpose,
                "approved_argument_keys": str(
                    item.metadata.get("conversation_argument_keys", "")
                ),
                "supports_self_target": bool(
                    str(item.metadata.get("conversation_self_target_field", "")).strip()
                ),
            }
            for item in candidates
        ]
        result = self.client.complete(
            system=(
                "Interpret the human message only as a provider-neutral governed action. "
                "Choose only from the supplied registered capabilities. Never choose or name "
                "a provider, connector, agent, tool, URL, credential, secret, or shell command. "
                "Return only arguments explicitly supported by the selected capability metadata. "
                "For first-person targets such as 'me' or 'myself', set self_target=true and do "
                "not invent or return the person's address; Jason resolves that from its own "
                "identity binding. If this is not an imperative/requested action, resolved=false."
            ),
            user=json.dumps(
                {
                    "text": text,
                    "organization_scope": organization_id,
                    "client_scope_present": client_id is not None,
                    "candidates": candidate_metadata,
                },
                sort_keys=True,
            ),
            schema=schema,
            # Action arguments can contain human-authored text, so keep a larger
            # budget than read-only classification while still preventing an
            # unbounded local generation from consuming the Teams ingress window.
            max_output_tokens=256,
        )
        if result.get("resolved") is not True:
            return None
        return {
            "capability_name": result.get("capability_name"),
            "arguments": result.get("arguments", {}),
            "self_target": result.get("self_target") is True,
        }

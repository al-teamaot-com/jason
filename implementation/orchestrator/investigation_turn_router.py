"""Provider-independent routing into Jason's investigation engine.

This component answers only one question:

    What kind of conversational turn is this?

It does not identify resources, selectors, providers, capabilities, fields,
operations, evidence, or execution strategy.

Execution authority remains entirely outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping, Protocol


class StructuredTurnRoutingClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


class InvestigationTurnKind(str, Enum):
    INFORMATION = "information"
    ACTION = "action"
    CONVERSATION = "conversation"
    CLARIFY = "clarify"


@dataclass(frozen=True, slots=True)
class InvestigationTurnRoute:
    kind: InvestigationTurnKind


@dataclass(frozen=True, slots=True)
class InvestigationTurnRouter:
    client: StructuredTurnRoutingClient

    def route(
        self,
        *,
        human_text: str,
    ) -> InvestigationTurnRoute:
        text = human_text.strip()

        if not text:
            raise ValueError(
                "turn routing requires non-empty human text"
            )

        result = self.client.complete(
            system=_SYSTEM,
            user=json.dumps(
                {
                    "request": text,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_SCHEMA,
            max_output_tokens=80,
        )

        if not isinstance(result, Mapping):
            raise ValueError(
                "turn routing result must be an object"
            )

        try:
            kind = InvestigationTurnKind(
                str(result["kind"]).strip()
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                "turn routing returned invalid kind"
            ) from exc

        return InvestigationTurnRoute(
            kind=kind,
        )


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
    ],
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "information",
                "action",
                "conversation",
                "clarify",
            ],
        },
    },
}


_SYSTEM = """
Classify the human turn at a high conversational level only.

Return information when the human wants Jason to learn, inspect, find,
explain, correlate, diagnose, troubleshoot, verify, compare, summarize, or
answer something using available governed observations.

Return action when the human is asking Jason to change, create, delete,
restart, send, modify, configure, approve, execute, or otherwise cause an
external state change.

Return conversation for ordinary conversational interaction that does not
require governed operational information or an external action.

Return clarify only when missing human input prevents choosing safely because
the missing choice would materially change the target, authority, action,
risk, or meaning.

Important:
- Do not identify a resource.
- Do not extract or normalize identifiers.
- Do not construct selectors.
- Do not name or choose providers, connectors, capabilities, tools, APIs,
  operations, fields, databases, or implementation details.
- Do not answer the request.
- This classification grants no authority.
- When an information request is broad, diagnostic, or exploratory, it is
  still information.
- Return only the required structured object.
""".strip()

"""Evidence-grounded human answer generation for generic investigations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Protocol, Sequence


class StructuredInvestigationAnswerClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class InvestigationAnswerer:
    client: StructuredInvestigationAnswerClient

    def answer(
        self,
        *,
        human_text: str,
        evidence: Sequence[Mapping[str, Any]],
    ) -> str:
        if not human_text.strip():
            raise ValueError(
                "investigation answer requires human text"
            )

        if not evidence:
            raise ValueError(
                "investigation answer requires governed evidence"
            )

        result = self.client.complete(
            system=_SYSTEM,
            user=json.dumps(
                {
                    "request": human_text,
                    "governed_evidence": [
                        dict(item)
                        for item in evidence
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_SCHEMA,
            max_output_tokens=700,
        )

        answer = str(
            result.get(
                "answer",
                "",
            )
        ).strip()

        if not answer:
            raise ValueError(
                "investigation answerer returned empty text"
            )

        return answer


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "answer",
    ],
    "properties": {
        "answer": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
        },
    },
}


_SYSTEM = """
You are Jason's technician-facing evidence answer component.

Answer the human request using ONLY the supplied governed evidence.

Rules:
- Do not invent facts.
- Do not assume an absent value is false, disabled, missing, or zero.
- Distinguish unavailable evidence from confirmed negative evidence.
- If the evidence only partially answers the request, clearly say what is
  established and what is not established.
- Do not expose operation references, execution IDs, evidence IDs, capability
  names, provider IDs, connector names, APIs, field paths, or other internal
  routing details.
- Do not expose redacted values or attempt to reconstruct them.
- Prefer a useful technician answer over a raw data dump.
- Explain relevant findings concisely.
- When appropriate, mention a useful next diagnostic step based only on the
  established evidence.
- Do not claim an action was performed unless the supplied evidence explicitly
  establishes that action.
- Return only the required structured object.
""".strip()

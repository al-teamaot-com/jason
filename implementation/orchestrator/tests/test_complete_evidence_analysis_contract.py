from dataclasses import dataclass

from orchestrator.investigation_execution import (
    InvestigationEvidenceWorkspace,
)
from orchestrator.simple_reasoning_loop import (
    SimpleReasoningLoop,
)


@dataclass
class Evidence:
    data: dict

    def model_view(self):
        return {
            "data": {
                "provider_data": {
                    "pages": [
                        {
                            "devices": [
                                {"id": index}
                                for index in range(12)
                            ]
                            + [
                                {
                                    "_truncated_sequence_items":
                                        238
                                }
                            ]
                        }
                    ]
                }
            }
        }


class Workspace:
    def __init__(self, entries):
        self._entries = tuple(entries)

    def entries(self):
        return self._entries


def test_complete_truncated_collection_requires_analysis():
    workspace = Workspace(
        [
            Evidence(
                data={
                    "discovery_complete": True,
                    "provider_data": {
                        "pages": [
                            {
                                "devices": [
                                    {"id": index}
                                    for index
                                    in range(250)
                                ]
                            }
                        ]
                    },
                }
            )
        ]
    )

    assert (
        SimpleReasoningLoop
        ._requires_complete_evidence_analysis(
            workspace
        )
        is True
    )


def test_incomplete_collection_does_not_claim_complete_analysis_contract():
    evidence = Evidence(
        data={
            "discovery_complete": False,
        }
    )

    workspace = Workspace(
        [evidence]
    )

    assert (
        SimpleReasoningLoop
        ._requires_complete_evidence_analysis(
            workspace
        )
        is False
    )

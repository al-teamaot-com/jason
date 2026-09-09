import json

from orchestrator.investigation_answer import (
    InvestigationAnswerer,
)


class Client:
    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "answer": (
                "The endpoint is reporting Windows and "
                "is identified as LAB-WEST-17."
            )
        }


def test_answerer_receives_only_supplied_governed_evidence():
    client = Client()

    result = InvestigationAnswerer(
        client=client
    ).answer(
        human_text="What do we know about LAB-WEST-17?",
        evidence=(
            {
                "resource_type": "endpoint",
                "data": {
                    "hostname": "LAB-WEST-17",
                    "operatingSystem": "Windows",
                },
            },
        ),
    )

    assert "LAB-WEST-17" in result

    payload = json.loads(
        client.calls[0]["user"]
    )

    assert (
        payload["governed_evidence"][0]
        ["data"]["operatingSystem"]
        == "Windows"
    )

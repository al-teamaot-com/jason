from dataclasses import dataclass

from orchestrator.evidence_query import (
    query_governed_evidence,
)


@dataclass
class Evidence:
    resource_type: str
    data: dict


def _devices():
    records = []

    for index in range(758):
        if index < 317:
            operating_system = (
                "Microsoft Windows 10 Pro"
            )
        else:
            operating_system = (
                "Microsoft Windows 11 Pro"
            )

        records.append(
            {
                "uid": f"device-{index}",
                "hostname": f"HOST-{index}",
                "siteName": (
                    "Site A"
                    if index % 2 == 0
                    else "Site B"
                ),
                "operatingSystem":
                    operating_system,
            }
        )

    # Reproduce the connector's evidence shape: canonical matches plus
    # complete provider pages. The query must not double count.
    return Evidence(
        resource_type="endpoint",
        data={
            "resource_matches": [
                {
                    "resource_id":
                        record["uid"],
                    "hostname":
                        record["hostname"],
                    "site":
                        record["siteName"],
                }
                for record in records
            ],
            "provider_data": {
                "discovery_mode":
                    "authorized_account_collection",
                "pages": [
                    {
                        "devices":
                            records[:250],
                    },
                    {
                        "devices":
                            records[250:500],
                    },
                    {
                        "devices":
                            records[500:750],
                    },
                    {
                        "devices":
                            records[750:],
                    },
                ],
            },
            "discovery_complete": True,
        },
    )


def test_count_uses_complete_collection_not_model_excerpt():
    result = query_governed_evidence(
        (_devices(),),
        action="count",
        resource_type="endpoint",
        field="operatingSystem",
        comparison="contains",
        value="Windows 10",
        group_by="",
        select_fields=(),
        limit=100,
    )

    assert result["records_examined"] == 758
    assert result["count"] == 317
    assert result["source_complete"] is True


def test_group_count_works_across_complete_collection():
    result = query_governed_evidence(
        (_devices(),),
        action="group_count",
        resource_type="endpoint",
        field="operatingSystem",
        comparison="contains",
        value="Windows 10",
        group_by="siteName",
        select_fields=(),
        limit=100,
    )

    assert result["count"] if "count" in result else True
    assert sum(
        item["count"]
        for item in result["groups"]
    ) == 317

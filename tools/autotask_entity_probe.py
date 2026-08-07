#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
CLI_SOURCE = IMPLEMENTATION_ROOT / "cli" / "src"

for source in (IMPLEMENTATION_ROOT, CLI_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_cli.runtime import ProviderHttpError, build_autotask_connector

COMPANY_ID = 208


def probe(capability: str, arguments: dict[str, object]) -> None:
    connector = build_autotask_connector()
    request = ConnectorRequest(
        context=ConnectorContext(
            correlation_id=f"probe-{capability}",
            principal_id="operator-al",
            organization_id="aot",
            client_id=str(COMPANY_ID),
            capability=capability,
            mode="observe",
        ),
        arguments=arguments,
    )
    try:
        result = connector.execute(request)
    except ProviderHttpError as exc:
        print(f"{capability}: HTTP_{exc.status_code}")
        return
    except Exception as exc:
        print(f"{capability}: {exc.__class__.__name__}")
        return

    if capability.endswith(".search"):
        items = result.data.get("items")
        count = len(items) if isinstance(items, list) else "INVALID"
        print(f"{capability}: OK items={count}")
    else:
        item = result.data.get("item")
        print(f"{capability}: OK item={'yes' if isinstance(item, dict) else 'no'}")


def search(field: str) -> dict[str, object]:
    return {
        "search": (
            '{"MaxRecords":2,"filter":[{"op":"eq","field":"'
            + field
            + '","value":'
            + str(COMPANY_ID)
            + '}]} '
        ).strip()
    }


def main() -> int:
    probe("autotask.company.get", {"company_id": COMPANY_ID})
    probe("autotask.contact.search", search("companyID"))
    probe("autotask.configuration.search", search("companyID"))
    probe("autotask.ticket.search", search("companyID"))
    probe("autotask.contract.search", search("companyID"))
    probe("autotask.project.search", search("companyID"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from connectors.core.contracts import (
    ConnectorContext,
    ConnectorRequest,
)

from jason_cli.runtime import build_autotask_connector


def execute_autotask(
    *,
    capability: str,
    arguments: Mapping[str, Any],
    correlation_id: str,
) -> Mapping[str, Any]:
    connector = build_autotask_connector()

    result = connector.execute(
        ConnectorRequest(
            context=ConnectorContext(
                correlation_id=correlation_id,
                principal_id="jason-cli-user",
                organization_id="team-aot",
                client_id=None,
                capability=capability,
                mode="observe",
            ),
            arguments=arguments,
        )
    )

    return result.data


def read_search_file(path: Path) -> str:
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise ValueError(
            f"Search file is unavailable: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Search file contains invalid JSON: {path}"
        ) from error

    if not isinstance(parsed, Mapping):
        raise ValueError(
            "Search file must contain a JSON object."
        )

    return json.dumps(
        parsed,
        separators=(",", ":"),
    )


def print_result(data: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def run_describe(entity: str) -> int:
    data = execute_autotask(
        capability="autotask.entity.describe",
        arguments={"entity": entity},
        correlation_id=f"cli-autotask-describe-{entity}",
    )
    print_result(data)
    return 0


def run_get(entity: str, entity_id: int) -> int:
    data = execute_autotask(
        capability="autotask.entity.get",
        arguments={
            "entity": entity,
            "entity_id": entity_id,
        },
        correlation_id=(
            f"cli-autotask-get-{entity}-{entity_id}"
        ),
    )
    print_result(data)
    return 0


def run_query(
    entity: str,
    search_file: Path,
) -> int:
    search = read_search_file(search_file)

    data = execute_autotask(
        capability="autotask.entity.query",
        arguments={
            "entity": entity,
            "search": search,
        },
        correlation_id=f"cli-autotask-query-{entity}",
    )
    print_result(data)
    return 0

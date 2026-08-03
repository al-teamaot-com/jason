from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from jason_cli.autotask import (
    run_describe,
    run_get,
    run_query,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jason",
        description="Project Jason command-line interface",
    )

    platform_parsers = parser.add_subparsers(
        dest="platform",
        required=True,
    )

    autotask = platform_parsers.add_parser(
        "autotask",
        help="Use the governed Autotask integration.",
    )

    commands = autotask.add_subparsers(
        dest="command",
        required=True,
    )

    describe = commands.add_parser(
        "describe",
        help="Describe an approved Autotask entity.",
    )
    describe.add_argument("entity")

    get = commands.add_parser(
        "get",
        help="Retrieve an approved Autotask entity by ID.",
    )
    get.add_argument("entity")
    get.add_argument("entity_id", type=int)

    query = commands.add_parser(
        "query",
        help="Query an approved Autotask entity.",
    )
    query.add_argument("entity")
    query.add_argument(
        "--search-file",
        required=True,
        type=Path,
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        if arguments.platform == "autotask":
            if arguments.command == "describe":
                return run_describe(arguments.entity)

            if arguments.command == "get":
                return run_get(
                    arguments.entity,
                    arguments.entity_id,
                )

            if arguments.command == "query":
                return run_query(
                    arguments.entity,
                    arguments.search_file,
                )

        parser.error("Unsupported command.")
        return 2

    except (RuntimeError, ValueError) as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

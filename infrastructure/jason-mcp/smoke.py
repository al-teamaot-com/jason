import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


RESOURCE_ID = "69571572-83f7-1e33-9cdf-01717d4e74a4"


def dump(label, result):
    print(label + "_ERROR=", result.is_error)
    print(label + "_RESULT=")

    if result.structured_content is not None:
        print(
            json.dumps(
                result.structured_content,
                indent=2,
                default=str,
            )[:12000]
        )
    else:
        for item in result.content:
            value = getattr(item, "text", None)
            if value:
                print(value[:12000])


async def main():
    async with streamable_http_client(
        "http://127.0.0.1:8765/mcp"
    ) as (read_stream, write_stream):

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            tools = await session.list_tools()

            print("MCP_TOOL_COUNT=", len(tools.tools))

            for tool in tools.tools:
                print("MCP_TOOL=", tool.name)

            alerts = await session.call_tool(
                "search_endpoint_alerts",
                {
                    "resource_id": RESOURCE_ID,
                    "max_results": 50,
                },
            )

            dump("MCP_ALERTS", alerts)

            software = await session.call_tool(
                "list_endpoint_software",
                {
                    "resource_id": RESOURCE_ID,
                    "max_results": 100,
                },
            )

            dump("MCP_SOFTWARE", software)

            failed = bool(
                alerts.is_error
                or software.is_error
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

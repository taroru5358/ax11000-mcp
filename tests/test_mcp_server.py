"""stdio経由のMCPサーバスモークテスト (実機アクセスなし)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]
DUMMY_PASSWORD = "dummy-test"


def _server_params() -> StdioServerParameters:
    # stdio_client は env 未指定だと一部の変数しか子プロセスに渡さないため明示する
    return StdioServerParameters(
        command="uv",
        args=["run", "tplink-router-mcp"],
        cwd=str(REPO_ROOT),
        env={**get_default_environment(), "ROUTER_PASSWORD": DUMMY_PASSWORD},
    )


def _run(coro):
    return asyncio.run(coro)


async def _session_call(tool: str, args: dict):
    async with (
        stdio_client(_server_params()) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await session.call_tool(tool, args)


def test_stdio_list_tools():
    async def main():
        async with (
            stdio_client(_server_params()) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await session.list_tools()

    tools = _run(main())
    names = {t.name for t in tools.tools}
    assert {"session_info", "list_endpoints", "raw_request"} <= names


def test_stdio_session_info_no_secret_leak():
    result = _run(_session_call("session_info", {}))
    body = json.loads(result.content[0].text)
    assert body["password_set"] is True
    assert DUMMY_PASSWORD not in json.dumps(body)


def test_stdio_list_endpoints():
    result = _run(_session_call("list_endpoints", {}))
    body = json.loads(result.content[0].text)
    assert len(body["endpoints"]) >= 10

"""stdio経由のMCPサーバスモークテスト (実機アクセスなし)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


async def _session_call(tool: str, args: dict):
    params = StdioServerParameters(
        command="uv",
        args=["run", "ax11000-mcp"],
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return await session.call_tool(tool, args)


def test_stdio_list_tools(monkeypatch):
    monkeypatch.setenv("ROUTER_PASSWORD", "dummy-test")

    async def main():
        params = StdioServerParameters(
            command="uv",
            args=["run", "ax11000-mcp"],
            cwd=str(REPO_ROOT),
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            return await session.list_tools()

    tools = _run(main())
    names = {t.name for t in tools.tools}
    assert {"session_info", "list_endpoints", "raw_request"} <= names


def test_stdio_session_info_no_secret_leak(monkeypatch):
    monkeypatch.setenv("ROUTER_PASSWORD", "dummy-test")

    result = _run(_session_call("session_info", {}))
    body = json.loads(result.content[0].text)
    assert body["password_set"] is True
    assert "dummy-test" not in json.dumps(body)


def test_stdio_list_endpoints(monkeypatch):
    monkeypatch.setenv("ROUTER_PASSWORD", "dummy-test")

    result = _run(_session_call("list_endpoints", {}))
    body = json.loads(result.content[0].text)
    assert len(body["endpoints"]) >= 10

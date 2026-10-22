"""Optional end-to-end stdio MCP smoke test (requires mcp SDK)."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py"))],
            env={**os.environ, "GDN_BRAIN_DB": str(Path(tmp)/"brain.sqlite3")}
        )
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {t.name for t in listed.tools}
                assert names == {"brain_list_projects","brain_get_project",
                                 "brain_save_project","brain_add_checkpoint","brain_dashboard"}, names
                created = await session.call_tool("brain_save_project", arguments={
                    "project_id":"mcp-test", "name":"MCP Smoke Test",
                    "next_action":"Verify listing"})
                assert not created.is_error, created
                fetched = await session.call_tool("brain_get_project",arguments={
                    "project_id":"mcp-test"})
                assert not fetched.is_error, fetched
                l = await session.call_tool("brain_list_projects", arguments={})
                assert not l.is_error, l
                print("PASS: MCP initialize, tools/list, create, read, list")

if __name__=="__main__":
    asyncio.run(main())

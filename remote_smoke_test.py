import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).parent
URL=os.environ.get("GDN_BRAIN_TEST_URL","http://127.0.0.1:9865/mcp")

async def main():
    import urllib.request, urllib.error
    path=Path(os.environ.get("GDN_BRAIN_TOKENS",str(Path.home()/".config/gdn-shared-brain/remote-tokens.json")))
    keys=json.loads(path.read_text())
    for header in (None, "Bearer invalid"):
        headers={"Accept": "application/json, text/event-stream","Content-Type":"application/json"}
        if header: headers["Authorization"]=header
        req=urllib.request.Request(URL,data=b"{}",headers=headers,method="POST")
        try:
            urllib.request.urlopen(req,timeout=4)
            raise AssertionError("unauthenticated request accepted")
        except urllib.error.HTTPError as e:
            assert e.code==401,e.code
    import httpx2
    for level,expected in (("reader",{"brain_list_projects","brain_get_project","brain_dashboard"}),
                           ("writer",{"brain_list_projects","brain_get_project","brain_dashboard","brain_save_project","brain_add_checkpoint"})):
        async with httpx2.AsyncClient(headers={"Authorization":"Bearer "+keys[level]}, trust_env=False) as client:
            async with streamable_http_client(URL,http_client=client) as (read,write):
                async with ClientSession(read,write) as s:
                    await s.initialize()
                    tools=await s.list_tools()
                    names={x.name for x in tools.tools}
                    assert names==expected,(level,names)
                    fetched=await s.call_tool("brain_list_projects",arguments={})
                    assert not fetched.is_error,(level,fetched)
                    print("PASS HTTP MCP",level,"tools",len(names))
    print("PASS unauthorized requests blocked")

asyncio.run(main())

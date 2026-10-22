"""Authenticated stateless HTTP MCP endpoint (never put tokens in the public repo)."""
from __future__ import annotations
import asyncio
import hmac
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from gdn_brain import DEFAULT_DB, get_project, list_projects
from dashboard import get_dashboard
from mcp_server import app as write_app
from oauth_bridge import app as oauth_app, provider as oauth_provider, RESOURCE as OAUTH_RESOURCE

DB = os.environ.get("GDN_BRAIN_DB", str(DEFAULT_DB))
PUBLIC_HOST = os.environ.get("GDN_BRAIN_PUBLIC_HOST", "localhost")
EXTRA_ORIGINS = [x.strip() for x in os.environ.get("GDN_BRAIN_ALLOWED_ORIGINS","https://grok.com,https://chatgpt.com").split(",") if x.strip()]
TOKENS_PATH = Path(os.environ.get("GDN_BRAIN_TOKENS", "~/.config/gdn-shared-brain/remote-tokens.json")).expanduser()
READER = MCPServer("GDN Shared Brain Read-only")

@READER.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_list_projects(search: str = "", status: str = "") -> list[dict]:
    """List project names, statuses, priorities, and next actions."""
    return list_projects(DB, search=search, status=status)

@READER.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_dashboard() -> dict:
    """Read the cross-agent project overview and next steps."""
    return get_dashboard()

@READER.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_get_project(project_id: str) -> dict:
    """Read a project and its latest checkpoints."""
    return get_project(DB, id=project_id) or {"error":"project_not_found"}

def make_mcp(server):
    return server.streamable_http_app(
        stateless_http=True, json_response=True, max_request_body_size=1_048_576,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[PUBLIC_HOST, PUBLIC_HOST+":443",
                           "127.0.0.1:9865","localhost:9865"],
            allowed_origins=EXTRA_ORIGINS + ["https://"+PUBLIC_HOST])
    )

reader_asgi = make_mcp(READER)
writer_asgi = make_mcp(write_app)

class ProtectedMCP:
    def __init__(self):
        self.buckets = defaultdict(deque)
        self._tokens = self.load()

    @staticmethod
    def load():
        path = TOKENS_PATH
        if path.stat().st_mode & 0o077:
            raise RuntimeError("Token file must be owner-only")
        obj = json.loads(path.read_text())
        assert all(isinstance(obj.get(k),str) and len(obj[k])>=40 for k in ("reader","writer"))
        assert obj["reader"] != obj["writer"]
        return obj

    async def __call__(self, scope, receive, send):
        if scope["type"]=="lifespan":
            # MCP ASGI lifespan context is required to initialise session managers.
            # Registered via parent starlette on startup, not here.
            await self._lifespan(scope, receive, send)
            return
        if scope["type"]!="http":
            return await self._reject(send,403,"Forbidden")
        path=scope.get("path","")
        if path in ("/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp",
                    "/.well-known/oauth-authorization-server",
                    "/authorize","/token","/register","/oauth/approve"):
            return await oauth_app(scope,receive,send)
        hdr={k.lower():v for k,v in scope.get("headers",[])}
        auth=hdr.get(b"authorization",b"").decode("ascii","ignore")
        provided=auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        access = None
        for label,value in self._tokens.items():
            if hmac.compare_digest(provided,value):
                access=label
        if not access and provided:
            oauth=await oauth_provider.load_access_token(provided)
            if oauth and oauth.resource==OAUTH_RESOURCE and "brain:read" in oauth.scopes:
                access="oauth-read"
        if not access:
            challenge=("Bearer realm=\"GDN Shared Brain\", "
              "resource_metadata=\"https://"+PUBLIC_HOST+
              "/.well-known/oauth-protected-resource\", scope=\"brain:read\"")
            return await self._reject(send,401,"Unauthorized",challenge.encode())
        now=time.monotonic()
        bucket=self.buckets[access]
        while bucket and now-bucket[0]>60: bucket.popleft()
        if len(bucket)>=120:
            return await self._reject(send,429,"Too Many Requests")
        bucket.append(now)
        await (writer_asgi if access=="writer" else reader_asgi)(scope,receive,send)

    async def _lifespan(self,scope,receive,send):
        # Run both MCP session manager lifespans in parallel.
        from contextlib import AsyncExitStack
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(reader_asgi.router.lifespan_context(reader_asgi))
            await stack.enter_async_context(writer_asgi.router.lifespan_context(writer_asgi))
            while True:
                event=await receive()
                if event["type"]=="lifespan.startup":
                    await send({"type":"lifespan.startup.complete"})
                elif event["type"]=="lifespan.shutdown":
                    await send({"type":"lifespan.shutdown.complete"})
                    break

    @staticmethod
    async def _reject(send,code,body,challenge=None):
        headers=[(b"content-type",b"text/plain; charset=utf-8"),
                 (b"cache-control",b"no-store"),
                 (b"x-content-type-options",b"nosniff")]
        if challenge:headers.append((b"www-authenticate",challenge))
        await send({"type":"http.response.start","status":code,"headers":headers})
        await send({"type":"http.response.body","body":body.encode()})

app = ProtectedMCP()

"""Single-owner OAuth 2.1 bridge for URL-only MCP clients.

Uses the official MCP SDK OAuth routes: DCR, PKCE, protected resource metadata.
Owner approval requires a server-side private password; OAuth tokens are read-only.
"""
from __future__ import annotations
import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route
from starlette.applications import Starlette
from mcp.server.auth.provider import (
    OAuthClientInformationFull, AuthorizationParams, AuthorizationCode,
    AccessToken, RefreshToken, OAuthToken
)
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import ClientRegistrationOptions

HOST = os.environ.get("GDN_BRAIN_PUBLIC_HOST", "localhost")
ISSUER = "https://" + HOST
RESOURCE = ISSUER + "/mcp"
ROOT = Path(os.environ.get("GDN_BRAIN_TOKENS", "~/.config/gdn-shared-brain/remote-tokens.json")).expanduser().parent
AUTH_DB = ROOT / "oauth.sqlite3"
APPROVAL_PATH = ROOT / "oauth-owner-password"
RL = {}

def tokenhash(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def connect():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    c = sqlite3.connect(str(AUTH_DB),timeout=10)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pending(id_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL,
          payload TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY, data TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, kind TEXT NOT NULL,
          client_id TEXT NOT NULL, scopes TEXT NOT NULL, resource TEXT,
          expires INTEGER NOT NULL);
    """)
    c.commit();os.chmod(AUTH_DB,0o600)
    return c

def bootstrap_password():
    if not APPROVAL_PATH.exists():
        fd=os.open(APPROVAL_PATH,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"w") as f: f.write(secrets.token_urlsafe(24)+"\n")
    if APPROVAL_PATH.stat().st_mode & 0o077:
        raise RuntimeError("Owner approval credential must be owner-only")
    return APPROVAL_PATH.read_text().strip()

class Provider:
    async def get_client(self, client_id:str):
        with connect() as c:
            r=c.execute("SELECT data FROM clients WHERE id=?",(client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(r["data"]) if r else None

    async def register_client(self, client_info):
        # Dynamic client registration cannot authorize itself. Owner must approve.
        for u in client_info.redirect_uris or []:
            parsed=urlparse(str(u))
            if parsed.scheme!="https" and not (parsed.scheme=="http" and parsed.hostname in ("localhost","127.0.0.1","[::1]")):
                raise ValueError("Only HTTPS or loopback callback URLs accepted")
        with connect() as c:
            c.execute("INSERT INTO clients(id,data) VALUES(?,?)",
                      (client_info.client_id,client_info.model_dump_json()))

    async def authorize(self, client:OAuthClientInformationFull, params:AuthorizationParams):
        approval_id=secrets.token_urlsafe(24)
        payload={"state":params.state,"scopes":params.scopes or ["brain:read"],
                 "code_challenge":params.code_challenge,"redirect_uri":str(params.redirect_uri),
                 "redirect_uri_provided_explicitly":params.redirect_uri_provided_explicitly,
                 "resource":params.resource or RESOURCE}
        with connect() as c:
            c.execute("INSERT INTO pending(id_hash,client_id,payload,expires) VALUES(?,?,?,?)",
                 (tokenhash(approval_id),client.client_id,json.dumps(payload),int(time.time())+600))
        return ISSUER+"/oauth/approve?request="+approval_id

    async def load_authorization_code(self,client,authorization_code):
        with connect() as c:
            r=c.execute("SELECT data,expires FROM codes WHERE hash=?",(tokenhash(authorization_code),)).fetchone()
        if not r or r["expires"]<time.time():return None
        d=json.loads(r["data"])
        if d["client_id"]!=client.client_id:return None
        return AuthorizationCode.model_validate(d)

    async def exchange_authorization_code(self,client,authorization_code):
        data=json.loads(authorization_code.model_dump_json())
        h=tokenhash(authorization_code.code)
        with connect() as c:
            c.execute("BEGIN IMMEDIATE")
            deleted=c.execute("DELETE FROM codes WHERE hash=? AND expires>?",(h,int(time.time())))
            if deleted.rowcount!=1:raise RuntimeError("OAuth code already used")
            access,refresh=secrets.token_urlsafe(40),secrets.token_urlsafe(40)
            now=int(time.time())
            r=data.get("resource") or RESOURCE
            if r!=RESOURCE: raise ValueError("Invalid OAuth resource")
            scopes=["brain:read"]
            c.execute("INSERT INTO tokens VALUES(?,?,?,?,?,?)",
                      (tokenhash(access),"access",client.client_id,json.dumps(scopes),RESOURCE,now+3600))
            c.execute("INSERT INTO tokens VALUES(?,?,?,?,?,?)",
                      (tokenhash(refresh),"refresh",client.client_id,json.dumps(scopes),RESOURCE,now+30*86400))
        return OAuthToken(access_token=access,refresh_token=refresh,expires_in=3600,scope="brain:read")

    async def load_refresh_token(self,client,refresh_token):
        with connect() as c:
            r=c.execute("SELECT * FROM tokens WHERE hash=? AND kind='refresh' AND expires>?",
                        (tokenhash(refresh_token),int(time.time()))).fetchone()
        if not r or r["client_id"]!=client.client_id:return None
        return RefreshToken(token=refresh_token,client_id=client.client_id,scopes=json.loads(r["scopes"]),
                            expires_at=r["expires"],resource=r["resource"])

    async def exchange_refresh_token(self,client,refresh_token,scopes):
        with connect() as c:
            c.execute("BEGIN IMMEDIATE")
            deleted=c.execute("DELETE FROM tokens WHERE hash=? AND kind='refresh'",(tokenhash(refresh_token.token),))
            if deleted.rowcount!=1: raise RuntimeError("OAuth refresh already used")
            now=int(time.time())
            access,new_refresh=secrets.token_urlsafe(40),secrets.token_urlsafe(40)
            c.execute("INSERT INTO tokens VALUES(?,?,?,?,?,?)",
                 (tokenhash(access),"access",client.client_id,'["brain:read"]',RESOURCE,now+3600))
            c.execute("INSERT INTO tokens VALUES(?,?,?,?,?,?)",
                 (tokenhash(new_refresh),"refresh",client.client_id,'["brain:read"]',RESOURCE,now+30*86400))
        return OAuthToken(access_token=access,refresh_token=new_refresh,expires_in=3600,scope="brain:read")

    async def load_access_token(self,token):
        with connect() as c:
            r=c.execute("SELECT * FROM tokens WHERE hash=? AND kind='access' AND expires>?",
                        (tokenhash(token),int(time.time()))).fetchone()
        if not r:return None
        if r["resource"]!=RESOURCE:return None
        return AccessToken(token=token,client_id=r["client_id"],scopes=json.loads(r["scopes"]),
                           expires_at=r["expires"],resource=r["resource"])

    async def revoke_token(self,token):
        with connect() as c:
            c.execute("DELETE FROM tokens WHERE hash=?",(tokenhash(token.token),))

provider=Provider()
bootstrap_password()
connect().close()

async def approve_page(request:Request):
    rid=request.query_params.get("request","")
    if len(rid)>100 or not rid:return PlainTextResponse("Not found",status_code=404)
    with connect() as c:
        row=c.execute("SELECT expires FROM pending WHERE id_hash=?",(tokenhash(rid),)).fetchone()
    if not row or row["expires"]<time.time():return PlainTextResponse("Authorization expired",status_code=410)
    page="""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>GDN Shared Brain access</title>
<style>body{font-family:system-ui;background:#151817;color:#f7f7f7;padding:28px;max-width:500px;margin:auto}
input,button{font:inherit;padding:15px;width:100%;box-sizing:border-box;margin-top:14px;border-radius:9px}
button{background:#e8efeb;color:#171817;border:0}p{line-height:1.6}</style>
<h2>Connect GDN Shared Brain</h2>
<p>Allow the requesting AI client to read project names, status and checkpoints. This grants READ ONLY access. The existing Hermes and Jack files remain separate.</p>
<form method="POST" action="/oauth/approve">
<input type="hidden" name="request" value="RID">
<input name="password" type="password" placeholder="Private owner approval password" required autocomplete="off">
<button type="submit">Authorize read-only access</button></form>
<p>Only proceed if you initiated the connector.</p></html>""".replace("RID",html.escape(rid,quote=True))
    return HTMLResponse(page,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer",
                                       "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"})

async def approve_submit(request:Request):
    form=await request.form()
    rid=str(form.get("request",""))
    entered=str(form.get("password",""))
    if not rid or len(rid)>100 or len(entered)>300:
        return PlainTextResponse("Invalid authorization request",status_code=400)
    # Limit attempts per pending request to slow down brute force attacks.
    key=tokenhash(rid)
    now=time.time()
    prev,count=RL.get(key,(now,0))
    if now-prev>600: prev,count=now,0
    if count>=8:return PlainTextResponse("Too many attempts. Restart connection.",status_code=429)
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT client_id,payload,expires FROM pending WHERE id_hash=?",(key,)).fetchone()
        if not row or row["expires"]<now:return PlainTextResponse("Expired request",status_code=410)
        if not hmac.compare_digest(entered,bootstrap_password()):
            RL[key]=(prev,count+1)
            return PlainTextResponse("Incorrect approval password",status_code=403)
        data=json.loads(row["payload"])
        if data["resource"]!=RESOURCE:
            return PlainTextResponse("Unrecognized resource",status_code=400)
        code=secrets.token_urlsafe(36)
        meta=AuthorizationCode(
            code=code,scopes=["brain:read"],expires_at=now+180,
            client_id=row["client_id"],code_challenge=data["code_challenge"],
            redirect_uri=data["redirect_uri"],
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            resource=RESOURCE)
        c.execute("INSERT INTO codes(hash,data,expires) VALUES(?,?,?)",
                  (tokenhash(code),meta.model_dump_json(),int(now)+180))
        c.execute("DELETE FROM pending WHERE id_hash=?",(key,))
    target=data["redirect_uri"]
    parsed=urlparse(target)
    query=dict(parse_qsl(parsed.query,keep_blank_values=True))
    query["code"]=code
    if data["state"] is not None:query["state"]=data["state"]
    return RedirectResponse(url=urlunparse(parsed._replace(query=urlencode(query))),status_code=302,
                            headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

auth_routes=create_auth_routes(provider,AnyHttpUrl(ISSUER),
    client_registration_options=ClientRegistrationOptions(
        enabled=True,valid_scopes=["brain:read"],default_scopes=["brain:read"]))
resource_routes=create_protected_resource_routes(AnyHttpUrl(RESOURCE),[AnyHttpUrl(ISSUER)],
    scopes_supported=["brain:read"],resource_name="GDN Shared Brain")
# Some clients fall back to the root well-known path.
async def resource_root(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"resource":RESOURCE,"authorization_servers":[ISSUER+"/"],
                         "scopes_supported":["brain:read"]})
app=Starlette(routes=auth_routes+resource_routes+[
    Route("/.well-known/oauth-protected-resource",resource_root,methods=["GET"]),
    Route("/oauth/approve",approve_page,methods=["GET"]),
    Route("/oauth/approve",approve_submit,methods=["POST"])
])

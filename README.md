# GDN Shared Brain

A tiny, local-first, provider-independent project memory for AI agents, using Python's built-in SQLite and an optional MCP adapter.

## Why

A conversation is not a project database. GDN Shared Brain records project state, current next actions, decisions, source references, and an append-only checkpoint history. AI clients can read the same state using MCP. No vector database, Redis, Postgres, cloud subscription or additional agent is required.

It is deliberately **not** a replacement for native agent memory. Hermes, Jack, and other systems can retain their existing memory, session history, schedulers, and project registries. Use Shared Brain as a shared index and checkpoint layer.

## Local install

Requires Python 3.10+.

    git clone https://github.com/Jhonny931/gdn-shared-brain.git
    cd gdn-shared-brain
    python3 gdn_brain.py init
    python3 gdn_brain.py list
    python3 gdn_brain.py save demo --name "Demo project" --priority p1 --next-action "Test the MCP connection" --actor manual
    python3 gdn_brain.py show demo
    python3 gdn_brain.py log demo "Test succeeded" --kind test --evidence verified --source-ref local:smoke-test

The default DB is ~/.local/share/gdn-shared-brain/brain.sqlite3, with restrictive permissions. Override with GDN_BRAIN_DB or CLI --db.

To change an existing project, read version with show, then supply --expected-version NUMBER. Version checks prevent silent concurrent overwrites.

## Optional MCP (local, stdio)

    python3 -m venv .venv
    .venv/bin/pip install -r requirements-mcp.txt
    .venv/bin/python mcp_server.py

Configure an MCP client to launch mcp_server.py using the same Python environment and GDN_BRAIN_DB. Available tools:

- brain_list_projects
- brain_get_project
- brain_save_project
- brain_add_checkpoint

**Do not publish the stdio endpoint to the internet.** A hosted HTTP MCP endpoint needs TLS, authentication, authorization, and rate limiting; it is not part of this minimal version.

## Hermes opt-in configuration

Hermes can use this shared project register through a separate MCP connection **without replacing its native MEMORY.md/USER.md**, routing or scheduled tasks. Copy only the mcp_servers configuration in examples/hermes-mcp.yaml into your existing Hermes config, adapt the absolute paths, and test in a separate Hermes session before enabling it for a running gateway. Do not overwrite your existing Hermes config or change memory.provider.

For other desktop MCP clients, run the same local Python process over stdio. For Grok and other cloud-hosted clients, a public HTTPS MCP service with real authentication is needed; the local stdio server is intentionally not reachable from the internet.

## Jack integration (read-only import)

If your machine has a Jack 100BTC project-registry/registry.json, use:

    python3 gdn_brain.py import-jack --registry-path /path/to/project-registry/registry.json

Only the ID and title of each record are indexed. The importer does **not** modify Jack, copy dossiers, include wallet details, or claim Jack's historical state is current. Imported projects are marked needs_review. Re-running the importer safely skips indexed IDs.

## Operating rules

- One shared SQLite database for project state, not shared passwords.
- Every substantial handoff writes a dated checkpoint with actor and source.
- Label factual checks verified only when the source is identifiable; otherwise use reported.
- Project updates require an expected version. Source systems continue operating independently.
- Never commit production DB, private event history, secret files, or client information to GitHub.
- Keep encrypted off-VPS backups. SQLite WAL means live backups should use SQLite's backup API.
- MCP clients should be authenticated and authorized before connecting over public networks.

## Roadmap

1. SQLite + CLI + local stdio MCP (this version).
2. Validate MCP tools using a dedicated test client and connect Hermes as an opt-in consumer without changing its native memory provider.
3. Add a secured HTTPS Streamable HTTP MCP endpoint for Grok/ChatGPT where supported.
4. Optionally add semantic recall (for example, Hindsight) as an independent capability.

## Development

    python3 -m unittest -v tests

MIT-licensed. Public source code includes synthetic examples only.

## Hosted MCP (optional)

The local stdio MCP works without a network service. The optional remote_server.py runs stateless Streamable HTTP MCP behind TLS and requires authentication.

Two different bearer credentials grant READ ONLY and READ/WRITE access. They are stored in an owner-only JSON file outside the source repo. The remote Python service should bind to loopback, never a public address. Configure GDN_BRAIN_TOKENS, GDN_BRAIN_PUBLIC_HOST and GDN_BRAIN_ALLOWED_ORIGINS. Use Caddy or an equivalent HTTPS reverse proxy to expose ONLY the /mcp endpoint. The remote server checks credentials before passing any request to the SDK.

Example development command (keep bound to loopback):

    GDN_BRAIN_PUBLIC_HOST=brain.example.com .venv/bin/python -m uvicorn remote_server:app --host 127.0.0.1 --port 9865

Run remote_smoke_test.py with GDN_BRAIN_TEST_URL set to your HTTPS endpoint after configuring private tokens. The test verifies both token scopes and rejects unauthorized requests.

For your personal setup, obtain the connection details LOCALLY by running show_connection.py --scope reader. Do not paste the bearer token into public chats, commits, screenshots or tickets.

Hosted clients such as Grok and ChatGPT require an account-level custom MCP connection that supports the required authentication. Merely exposing the HTTPS URL does not automatically connect those accounts. Respect their account and product limitations.

## Automated read-only source indexing

Run sync_sources.py to index native Hermes project titles and Jack project titles without changing either source. Re-runs are idempotent. Shared Brain records imported project states as needs_review until a separate factual check is performed.

## Mission Control dashboard

Run dashboard.py locally or invoke the MCP tool brain_dashboard. It returns a compact view of blocked, active and needs-review projects with next actions. It does NOT claim source project states are live-verified merely because they exist.

## Encrypted off-VPS backups

Set GDN_BRAIN_BACKUP_REPO to the name of an existing private repository. Run backup_private.py with authenticated GitHub CLI and the Python cryptography dependency (installed with requirements-mcp.txt). This creates an encrypted SQLite snapshot and uploads it off-site. Each run immediately downloads the encrypted result, decrypts it, verifies SQLite integrity and checks the restored contents match.

IMPORTANT: the recovery key is stored on the VPS at ~/.config/gdn-shared-brain/recovery.key. Save a separate copy in a trusted password manager or offline safe. If the VPS AND the recovery key are lost, encrypted backups cannot be decrypted.

Automatic scheduling on Linux may use systemd timers or cron. A real deployment must monitor backup failures and periodically test a full restore with its independently preserved recovery key.

An example Hermes skill is included under skills/gdn-shared-brain/SKILL.md. Use it as an additional tool skill without replacing native agent memory.

For GitHub Actions CI, copy examples/github-actions-test.yml to .github/workflows/test.yml using credentials with workflow write permission.

## Grok custom connector: OAuth instead of pasted API keys

Custom Grok connectors may offer only a name and MCP URL. For that surface,
the server supports OAuth 2.1 authorization-code + PKCE, dynamic client
registration, protected-resource discovery, scoped read-only access tokens,
refresh token rotation, and owner-controlled approval.

Example public HTTPS paths on your own domain:

- /mcp
- /.well-known/oauth-protected-resource
- /.well-known/oauth-protected-resource/mcp
- /.well-known/oauth-authorization-server
- /register
- /authorize
- /token
- /oauth/approve

Proxy all paths to the same local server through TLS; do not expose the
application's loopback port to the internet. Set GDN_BRAIN_PUBLIC_HOST to your
public host. The OAuth approval password is generated on first start in the
private directory alongside GDN_BRAIN_TOKENS. Obtain it on your trusted server
only; never commit it or paste it into a public chat. Login is read-only by
design; write-enabled access remains a separate manually provisioned bearer
token. Existing tokens and local Hermes MCP can coexist with OAuth.

Example endpoint for your own installation:
https://brain.example.com/mcp

Only authorize an OAuth request you initiated. Provider compatibility can
vary; use the provider's UI to complete the flow. For example, the Grok UI
may send the user to /oauth/approve after connector registration.

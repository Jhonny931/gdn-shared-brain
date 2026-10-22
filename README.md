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

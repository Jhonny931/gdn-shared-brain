---
name: gdn-shared-brain
description: Share project status, checkpoints and next actions safely across Hermes, Jack, Codex, Grok and ChatGPT via GDN Shared Brain MCP. Use when the user asks to resume/review projects, hand off work, or record completion.
---

# GDN Shared Brain

GDN Shared Brain is the shared project register; it does NOT replace native MEMORY.md / USER.md, profile memory, conversation history or cron jobs.

## Workflow

1. When asked for the full project overview, call brain_dashboard. For a specific unknown project ID, call brain_list_projects.
1a. Read brain_list_tasks to identify which actions belong to the user, this agent, or external partners. Do not treat tasks as completed merely because a file exists.
2. Call brain_get_project for latest status, next action, checkpoints and version.
3. Compare reported state with live files, source systems and test results before claiming work is done.
4. Do requested work with existing tools. NEVER store credentials, API keys, raw client data or full chat transcripts in Shared Brain.
5. After a significant milestone or blocker call brain_add_checkpoint. Set actor and source_ref; mark evidence verified only when supported by test, file, deployment or issue.
6. Update actual tasks with brain_save_task (owner=user/agent/external, status=todo/in_progress/blocked/done), passing their most recently read expected_version; check outcome.
7. When project next action or status changes, call brain_save_project with expected_version from brain_get_project. On a conflict re-read and reconcile.
8. For a paused project, do not continue implementation without a new user request. In particular, external Grok connector onboarding has been paused by the owner.

Jack's registry and Hermes native projects are read-only source indexes. Do not rewrite them through Shared Brain.

If MCP is offline, work normally but disclose that the Shared Brain checkpoint could not be saved.

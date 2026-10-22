"""MCP adapter for GDN Shared Brain; install optional mcp Python SDK."""
import os
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from gdn_brain import get_project, list_projects, put_project, add_checkpoint, DEFAULT_DB
from dashboard import get_dashboard
from brain_tasks import list_tasks,save_task

app = MCPServer("GDN Shared Brain")
DB = os.environ.get("GDN_BRAIN_DB", str(DEFAULT_DB))

@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_list_projects(search: str = "", status: str = "") -> list[dict]:
    """List projects, optionally filtered by search text or status."""
    return list_projects(DB, search=search, status=status)

@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_dashboard() -> dict:
    """Get mission-control overview: priorities, blockers, active projects and next actions."""
    return get_dashboard()

@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_get_project(project_id: str) -> dict:
    """Get a project including recent checkpoints and its current version."""
    project=get_project(DB,id=project_id)
    if project is None:return {"error":"project_not_found"}
    project["tasks"]=list_tasks(DB,project_id=project_id)
    return project

@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def brain_list_tasks(project_id: str = "", owner: str = "", status: str = "") -> list[dict]:
    """View outstanding and completed tasks. Filter by project, user/agent/external owner, or status."""
    return list_tasks(DB,project_id=project_id,owner=owner,status=status)

@app.tool()
def brain_save_task(task_id: str, project_id: str = "", title: str = "",
                    owner: str = "", status: str = "", priority: str = "",
                    actor: str = "mcp-agent",source_ref: str = "",
                    expected_version: int = 0) -> dict:
    """Create or update a task with optimistic concurrency. Read current task version first."""
    return save_task(DB,id=task_id,project_id=project_id,title=title or None,
        owner=owner or None,status=status or None,priority=priority or None,
        actor=actor,source_ref=source_ref,
        expected_version=expected_version or None)

@app.tool()
def brain_save_project(project_id: str, name: str = "", status: str = "",
                       priority: str = "", summary: str = "", next_action: str = "",
                       actor: str = "mcp-agent", source_ref: str = "",
                       expected_version: int = 0) -> dict:
    """Create or update a project. For updates pass the current version from brain_get_project."""
    return put_project(
        DB, id=project_id, name=name or None, status=status or None,
        priority=priority or None, summary=summary or None,
        next_action=next_action or None, actor=actor,
        source_ref=source_ref,
        expected_version=expected_version or None)

@app.tool()
def brain_add_checkpoint(project_id: str, detail: str, actor: str = "mcp-agent",
                         source_ref: str = "", evidence: str = "reported",
                         kind: str = "checkpoint") -> dict:
    """Append checkpoint, decision, blocker, test or note, including actor and evidence."""
    return add_checkpoint(DB, id=project_id, detail=detail,
                          actor=actor, source_ref=source_ref,
                          evidence=evidence, kind=kind)

if __name__ == "__main__":
    # Local-only stdio: does NOT expose unauthenticated HTTP.
    app.run()

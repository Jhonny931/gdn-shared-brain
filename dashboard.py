"""Agent-neutral mission-control overview of project state and owners."""
from datetime import datetime, timezone, timedelta
from gdn_brain import list_projects
from brain_tasks import list_tasks

def is_reference(p):
    return p["id"].startswith(("jack-100BTC-","jack-EXPERIMENT-",
        "hermes-default-","hermes-kisa-lab-","hermes-hermes-expert-"))

def get_dashboard(limit=12):
    projects=list_projects()
    tasks=list_tasks()
    core=[p for p in projects if not is_reference(p)]
    reference=[p for p in projects if is_reference(p)]
    statuses=("blocked","active","needs_review")
    focus=sorted((p for p in core if p["status"] in statuses),
        key=lambda p:(int(p["priority"][1]),statuses.index(p["status"]),p["name"].lower()))
    outstanding=[t for t in tasks if t["status"] in ("todo","in_progress","blocked")]
    user_tasks=[t for t in outstanding if t["owner"]=="user"]
    agent_tasks=[t for t in outstanding if t["owner"]=="agent"]
    cutoff=datetime.now(timezone.utc)-timedelta(days=7)
    changed=sum(1 for p in projects if datetime.fromisoformat(p["updated_at"])>=cutoff)
    def compact(p):
        return {k:p[k] for k in ("id","name","status","priority","next_action","updated_at","source_ref")}
    return {
        "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_records":len(projects),
        "main_projects":len(core),
        "reference_records":len(reference),
        "active":sum(p["status"]=="active" for p in core),
        "blocked":sum(p["status"]=="blocked" for p in core),
        "paused":sum(p["status"]=="paused" for p in core),
        "awaiting_review":sum(p["status"]=="needs_review" for p in core),
        "tasks_total":len(tasks),
        "tasks_outstanding":len(outstanding),
        "tasks_waiting_for_user":len(user_tasks),
        "user_actions":user_tasks[:30],
        "agent_actions":agent_tasks[:30],
        "cards_changed_last_7_days":changed,
        "focus":[compact(p) for p in focus[:max(1,min(int(limit),50))]],
        "data_quality":"Status refers to project workflow, not guaranteed service uptime. Imported projects may need independent confirmation. Timestamps refer to saved cards, not necessarily source-system events.",
    }

if __name__=="__main__":
    import json
    print(json.dumps(get_dashboard(),ensure_ascii=False,indent=2))

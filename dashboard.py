"""Agent-neutral summary of the shared project register."""
from datetime import datetime, timezone, timedelta
from gdn_brain import list_projects

def get_dashboard(limit=12):
    projects=list_projects()
    active=[p for p in projects if p["status"]=="active"]
    blocked=[p for p in projects if p["status"]=="blocked"]
    todo=[p for p in projects if p["status"]=="needs_review"]
    ready=[p for p in projects if p["status"] in ("active","blocked")]
    focus=(blocked+ready+todo)[:max(1,min(int(limit),50))]
    cutoff=datetime.now(timezone.utc)-timedelta(days=7)
    updates=sum(1 for p in projects
                if datetime.fromisoformat(p["updated_at"])>=cutoff)
    def compact(p):
        return {k:p[k] for k in ("id","name","status","priority","next_action","updated_at","source_ref")}
    return {
        "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total":len(projects),
        "active":len(active),
        "blocked":len(blocked),
        "awaiting_review":len(todo),
        "updated_last_7_days":updates,
        "focus":[compact(p) for p in focus],
        "data_quality":"Imported project statuses are needs_review until independently verified; changes in source repositories are not proof of completed work."
    }

if __name__=="__main__":
    import json
    print(json.dumps(get_dashboard(),ensure_ascii=False,indent=2))

"""Idempotent read-only source indexing; never modifies Hermes or Jack."""
from __future__ import annotations
import json
import os
import re
import sqlite3
from pathlib import Path
from gdn_brain import get_project,put_project,add_checkpoint,list_projects

def slug(value: str) -> str:
    out=re.sub(r"[^a-zA-Z0-9._-]+","-",str(value)).strip(".-").lower()
    return out[:70] or "unknown"

def put_source_card(pid,name,source_ref,summary,priority="p2"):
    name=str(name or pid).strip()[:200]
    old=get_project(id=pid)
    if old is None:
        put_project(id=pid,name=name,status="needs_review",priority=priority,
            summary=summary,next_action="Verify source state and decide next action",
            actor="source-sync",source_ref=source_ref)
        return "created"
    # Do not overwrite human/agent changes: imported cards are reference-only.
    if old["updated_by"]=="source-sync" and old["name"]!=name:
        put_project(id=pid,name=name,expected_version=old["version"],
            actor="source-sync",source_ref=source_ref)
        return "updated"
    return "unchanged"

def sync_hermes(home):
    result={"created":0,"updated":0,"unchanged":0,"unavailable":0}
    locations=[("default",home/".hermes/projects.db"),
               ("kisa-lab",home/".hermes/profiles/kisa-lab/projects.db"),
               ("hermes-expert",home/".hermes/profiles/hermes-expert/projects.db")]
    for scope,path in locations:
        if not path.is_file():
            result["unavailable"]+=1
            continue
        con=sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True)
        con.row_factory=sqlite3.Row
        try:
            rows=con.execute("SELECT id,slug,name,archived FROM projects").fetchall()
        finally:
            con.close()
        for r in rows:
            origin="hermes-project:"+scope+":"+str(r["id"])
            pid="hermes-"+scope+"-"+slug(r["slug"] or r["id"])
            status=put_source_card(pid,r["name"],origin,
                "Hermes native project index. Conversation memory stays in Hermes.")
            result[status]+=1
    return result

def sync_jack(home):
    path=Path(os.environ.get("JACK_REGISTRY_PATH",
        str(home/".hermes/profiles/kisa-lab/venture/100btc/project-registry/registry.json")))
    out={"created":0,"updated":0,"unchanged":0,"unavailable":0}
    if not path.is_file():
        out["unavailable"]+=1
        return out
    raw=json.loads(path.read_text())
    for item in raw.get("projects",[]):
        rid=str(item.get("id",""))
        if not rid:continue
        pid="jack-"+re.sub(r"[^a-zA-Z0-9._-]","-",rid)
        status=put_source_card(pid,item.get("title",rid),"jack:"+rid,
            "Imported index from Jack. Status must be independently verified.",
            priority="p3")
        out[status]+=1
    return out

def main():
    home=Path.home()
    print(json.dumps({"hermes":sync_hermes(home),"jack":sync_jack(home),
         "total":len(list_projects())},ensure_ascii=False))
if __name__=="__main__":
    main()

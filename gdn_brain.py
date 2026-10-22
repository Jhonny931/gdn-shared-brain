"""GDN Shared Brain: small, local-first project memory (Python stdlib only)."""
from __future__ import annotations
import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_DB = Path(os.environ.get("GDN_BRAIN_DB", "~/.local/share/gdn-shared-brain/brain.sqlite3")).expanduser()
STATUSES = {"needs_review", "idea", "active", "blocked", "paused", "done", "archived"}
PRIORITIES = {"p0", "p1", "p2", "p3"}
# Best-effort prevention, not a substitute for secrets management.
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]{15,}|sk-[A-Za-z0-9_-]{20,}|Bearer\s+\S+|-----BEGIN\s+[^-]*PRIVATE KEY-----|(?:api[_ -]?key|password|secret|token)\s*[:=]\s*\S+)", re.I)

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def safe(value, max_len=4000):
    value = str(value or "").strip()
    if len(value) > max_len:
        raise ValueError("Field too long")
    if SECRET.search(value):
        raise ValueError("Possible secret detected; store credentials outside Shared Brain")
    return value

def connect(db=DEFAULT_DB):
    db = Path(db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(db.parent, 0o700)
    con = sqlite3.connect(str(db), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA journal_mode=WAL")
    if db.exists():
        os.chmod(db, 0o600)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'needs_review',
        priority TEXT NOT NULL DEFAULT 'p2',
        summary TEXT NOT NULL DEFAULT '',
        next_action TEXT NOT NULL DEFAULT '',
        source_ref TEXT NOT NULL DEFAULT '',
        updated_by TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1
      );
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL REFERENCES projects(id),
        kind TEXT NOT NULL, detail TEXT NOT NULL,
        actor TEXT NOT NULL, source_ref TEXT NOT NULL,
        evidence TEXT NOT NULL DEFAULT 'reported',
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS events_project_idx ON events(project_id, id DESC);
    """)
    con.commit()
    return con

def put_project(db=DEFAULT_DB, *, id, name=None, status=None, priority=None,
                summary=None, next_action=None, actor="manual",
                source_ref="", expected_version=None):
    pid = safe(id, 100)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,99}", pid):
        raise ValueError("Project id should be 2-100 characters (letters, digits, ._-)")
    actor = safe(actor, 80); source_ref = safe(source_ref, 500)
    with connect(db) as con:
        con.execute("BEGIN IMMEDIATE")
        old = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if old is not None and (expected_version is None or int(expected_version) != old["version"]):
            raise ValueError("Project changed or expected_version missing; read again before updating")
        if old is None and expected_version is not None:
            raise ValueError("Project does not exist; create without expected_version")
        if old is None and not name:
            raise ValueError("name required for new projects")
        fields = dict(old) if old else {
            "id":pid, "name":"", "status":"needs_review", "priority":"p2",
            "summary":"", "next_action":"", "source_ref":"", "updated_by":"",
            "updated_at":"", "version":0
        }
        for k, val, limit in (
            ("name",name,200), ("status",status,40), ("priority",priority,10),
            ("summary",summary,4000), ("next_action",next_action,1000),
        ):
            if val is not None: fields[k] = safe(val, limit)
        if fields["status"] not in STATUSES: raise ValueError("Unknown status")
        if fields["priority"] not in PRIORITIES: raise ValueError("Unknown priority")
        fields.update(updated_at=timestamp(),updated_by=actor,
                      source_ref=source_ref or fields["source_ref"],
                      version=fields["version"]+1)
        con.execute("""
            INSERT INTO projects (id,name,status,priority,summary,next_action,
               source_ref,updated_by,updated_at,version)
            VALUES (:id,:name,:status,:priority,:summary,:next_action,
               :source_ref,:updated_by,:updated_at,:version)
            ON CONFLICT(id) DO UPDATE SET
               name=excluded.name,status=excluded.status,priority=excluded.priority,
               summary=excluded.summary,next_action=excluded.next_action,
               source_ref=excluded.source_ref,updated_by=excluded.updated_by,
               updated_at=excluded.updated_at,version=excluded.version
        """, fields)
        con.execute("""INSERT INTO events(project_id,kind,detail,actor,source_ref,evidence,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (pid, "created" if old is None else "updated",
                     "Project created" if old is None else "Project details updated",
                     actor, fields["source_ref"], "reported", timestamp()))
        return fields

def get_project(db=DEFAULT_DB, id=""):
    with connect(db) as con:
        row = con.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
        if row is None: return None
        result = dict(row)
        result["events"] = [dict(x) for x in con.execute(
            "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 30", (id,))]
        return result

def list_projects(db=DEFAULT_DB, search="", status=""):
    with connect(db) as con:
        q = "SELECT * FROM projects WHERE 1=1"; params=[]
        if status:
            q += " AND status=?"; params.append(status)
        if search:
            q += " AND (name LIKE ? OR id LIKE ? OR summary LIKE ? OR next_action LIKE ?)"
            params += ["%"+search+"%"]*4
        q += " ORDER BY CASE priority WHEN 'p0' THEN 0 WHEN 'p1' THEN 1 WHEN 'p2' THEN 2 ELSE 3 END,updated_at DESC"
        return [dict(x) for x in con.execute(q+" LIMIT 200", params)]

def add_checkpoint(db=DEFAULT_DB, *, id, detail, actor="manual", source_ref="",
                   evidence="reported", kind="checkpoint"):
    if evidence not in {"reported","verified"}:
        raise ValueError("evidence must be reported or verified")
    if kind not in {"checkpoint","decision","blocker","test","note"}:
        raise ValueError("Unsupported event kind")
    detail=safe(detail,10000); actor=safe(actor,80); source_ref=safe(source_ref,500)
    if evidence=="verified" and not source_ref:
        raise ValueError("Verified evidence requires a source_ref")
    with connect(db) as con:
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM projects WHERE id=?", (id,)).fetchone():
            raise ValueError("Project not found")
        cur=con.execute(
            "INSERT INTO events(project_id,kind,detail,actor,source_ref,evidence,created_at) VALUES(?,?,?,?,?,?,?)",
            (id,kind,detail,actor,source_ref,evidence,timestamp()))
        return {"event_id":cur.lastrowid,"project_id":id,"created_at":timestamp()}

def import_jack(db=DEFAULT_DB, registry_path=None):
    """Import a minimal index, never edit Jack's source files or copy entire dossiers."""
    if registry_path is None:
        registry_path=os.environ.get("JACK_REGISTRY_PATH")
    if not registry_path:
        raise ValueError("Provide --registry-path or JACK_REGISTRY_PATH")
    raw=json.loads(Path(registry_path).read_text(encoding="utf-8"))
    imported=[]; skipped=[]
    for p in raw.get("projects",[]):
        rid=str(p.get("id",""))
        pid="jack-"+re.sub("[^a-zA-Z0-9._-]","-",rid)
        if get_project(db,id=pid) is not None:
            skipped.append(pid);continue
        put_project(db,id=pid,name=str(p.get("title") or rid),
                    status="needs_review",priority="p3",
                    summary="Imported index from Jack. Status must be verified against Jack's live state.",
                    next_action="Verify source status and decide whether this is an active GDN project",
                    actor="jack-importer",source_ref="jack:"+rid)
        imported.append(pid)
    return {"imported":len(imported),"skipped":len(skipped),"ids":imported}

def main():
    p=argparse.ArgumentParser(description="GDN Shared Brain (local-first project memory)")
    p.add_argument("--db",default=str(DEFAULT_DB))
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init")
    ls=sub.add_parser("list");ls.add_argument("--search",default="");ls.add_argument("--status",default="")
    show=sub.add_parser("show");show.add_argument("id")
    save=sub.add_parser("save");save.add_argument("id")
    for k in ("name","status","priority","summary","next-action","actor","source-ref"):
        save.add_argument("--"+k)
    save.add_argument("--expected-version",type=int)
    log=sub.add_parser("log");log.add_argument("id");log.add_argument("detail")
    for k in ("actor","source-ref","evidence","kind"): log.add_argument("--"+k)
    imp=sub.add_parser("import-jack");imp.add_argument("--registry-path")
    args=p.parse_args();db=Path(args.db)
    if args.cmd=="init": con=connect(db);con.close();out={"db":str(db),"initialized":True}
    elif args.cmd=="list": out=list_projects(db,args.search,args.status)
    elif args.cmd=="show": out=get_project(db,args.id)
    elif args.cmd=="save":
        out=put_project(db,id=args.id,name=args.name,status=args.status,
            priority=args.priority,summary=args.summary,next_action=args.next_action,
            actor=args.actor or "manual",source_ref=args.source_ref or "",
            expected_version=args.expected_version)
    elif args.cmd=="log":
        out=add_checkpoint(db,id=args.id,detail=args.detail,actor=args.actor or "manual",
            source_ref=args.source_ref or "", evidence=args.evidence or "reported",
            kind=args.kind or "checkpoint")
    else: out=import_jack(db,args.registry_path)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

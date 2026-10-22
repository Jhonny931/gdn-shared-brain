"""Simple shared task queue: who acts next, what is blocked, what was done."""
from __future__ import annotations
import re
from gdn_brain import connect, DEFAULT_DB, safe, timestamp, add_checkpoint
TASK_STATES={"todo","in_progress","blocked","done","canceled"}
OWNERS={"user","agent","external"}
PRIORITIES={"p0","p1","p2","p3"}

def init(db=DEFAULT_DB):
    with connect(db) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          title TEXT NOT NULL, owner TEXT NOT NULL DEFAULT 'agent',
          status TEXT NOT NULL DEFAULT 'todo',priority TEXT NOT NULL DEFAULT 'p2',
          source_ref TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS task_project_idx ON tasks(project_id,status,priority);
        """)

def list_tasks(db=DEFAULT_DB, project_id="", owner="", status=""):
    init(db)
    sql="SELECT * FROM tasks WHERE 1=1"
    vals=[]
    if project_id:sql+=" AND project_id=?";vals.append(project_id)
    if owner:sql+=" AND owner=?";vals.append(owner)
    if status:sql+=" AND status=?";vals.append(status)
    sql+=" ORDER BY CASE status WHEN 'blocked' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END, CASE owner WHEN 'user' THEN 0 WHEN 'agent' THEN 1 ELSE 2 END,priority ASC, updated_at DESC LIMIT 300"
    with connect(db) as c:
        return [dict(r) for r in c.execute(sql,vals)]

def save_task(db=DEFAULT_DB, *, id, project_id="", title=None, owner=None, status=None,
              priority=None, actor="manual", source_ref="", expected_version=None):
    init(db)
    id=safe(id,100)
    if not re.fullmatch("[a-zA-Z0-9][a-zA-Z0-9._-]{1,99}",id):
        raise ValueError("Invalid task ID")
    actor=safe(actor,80);source_ref=safe(source_ref,500)
    with connect(db) as c:
        c.execute("BEGIN IMMEDIATE")
        old=c.execute("SELECT * FROM tasks WHERE id=?",(id,)).fetchone()
        if old and (expected_version is None or int(expected_version)!=old["version"]):
            raise ValueError("Task changed or expected_version missing")
        if not old and expected_version is not None:
            raise ValueError("Task does not yet exist")
        if not old and (not project_id or not title):
            raise ValueError("New task requires project_id and title")
        fields=dict(old) if old else dict(id=id,project_id=project_id,
            title="",owner="agent",status="todo",priority="p2",source_ref="",
            updated_by="",created_at=timestamp(),updated_at="",version=0)
        if old and project_id and old["project_id"]!=project_id:
            raise ValueError("Cannot move a task to another project")
        for k,v,max_length in (("title",title,300),("owner",owner,20),
            ("status",status,30),("priority",priority,10)):
            if v is not None:fields[k]=safe(v,max_length)
        if fields["owner"] not in OWNERS:raise ValueError("Invalid owner")
        if fields["status"] not in TASK_STATES:raise ValueError("Invalid task status")
        if fields["priority"] not in PRIORITIES:raise ValueError("Invalid task priority")
        fields.update(updated_by=actor,updated_at=timestamp(),
            source_ref=source_ref or fields["source_ref"],version=fields["version"]+1)
        c.execute("""INSERT INTO tasks(id,project_id,title,owner,status,priority,source_ref,updated_by,created_at,updated_at,version)
            VALUES(:id,:project_id,:title,:owner,:status,:priority,:source_ref,:updated_by,:created_at,:updated_at,:version)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,owner=excluded.owner,
              status=excluded.status,priority=excluded.priority,source_ref=excluded.source_ref,
              updated_by=excluded.updated_by,updated_at=excluded.updated_at,version=excluded.version""",fields)
        c.execute("INSERT INTO events(project_id,kind,detail,actor,source_ref,evidence,created_at) VALUES(?,?,?,?,?,?,?)",
            (fields["project_id"],"note",safe("Task "+id+" -> "+fields["status"],500),
             actor,fields["source_ref"],"reported",timestamp()))
    return fields

def get_task(db=DEFAULT_DB,id=""):
    init(db)
    with connect(db) as c:
        row=c.execute("SELECT * FROM tasks WHERE id=?",(id,)).fetchone()
        return dict(row) if row else None

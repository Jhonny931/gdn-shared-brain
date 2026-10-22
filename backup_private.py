"""Encrypted backup to a private GitHub repo with a remote restore test.

Requires cryptography and authenticated GitHub CLI; never prints the recovery key.
"""
import base64
import datetime
import hashlib
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from gdn_brain import DEFAULT_DB

REPO=os.environ.get("GDN_BRAIN_BACKUP_REPO","")
GH_BIN=os.environ.get("GDN_GH_BIN",shutil.which("gh") or "gh")
ROOT=Path(os.environ.get("GDN_BRAIN_BACKUP_HOME","~/.config/gdn-shared-brain")).expanduser()
KEY=ROOT/"recovery.key"
DB=Path(os.environ.get("GDN_BRAIN_DB",str(DEFAULT_DB))).expanduser()

def gh(endpoint, *, request=None):
    cmd=[GH_BIN,"api",endpoint]
    if request is not None:cmd+=["-X","PUT","--input","-"]
    p=subprocess.run(cmd,input=json.dumps(request) if request is not None else None,
                     capture_output=True,text=True,timeout=40)
    if p.returncode:
        raise RuntimeError("GitHub API failed: "+endpoint.rsplit("/",1)[-1])
    return json.loads(p.stdout)

def recovery_key():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(ROOT,0o700)
    if not KEY.exists():
        fd=os.open(str(KEY),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as f:f.write(Fernet.generate_key()+b"\n")
        print("New recovery key generated; off-server copy still needed.")
    if KEY.stat().st_mode & 0o077:
        raise RuntimeError("Recovery key permissions insecure")
    return Fernet(KEY.read_bytes().strip())

def verify_database(contents):
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/"restore.sqlite3"
        p.write_bytes(contents)
        c=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True)
        try:
            assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            return c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        finally:c.close()

def snapshot():
    if not DB.is_file():raise RuntimeError("Database missing")
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/"snapshot.sqlite3"
        src=sqlite3.connect(str(DB),timeout=30)
        dst=sqlite3.connect(str(p))
        try:src.backup(dst)
        finally:dst.close();src.close()
        return p.read_bytes()

def main():
    if not REPO or "/" not in REPO:
        raise RuntimeError("Set GDN_BRAIN_BACKUP_REPO to owner/private-repo")
    repo=gh(f"repos/{REPO}")
    if not repo.get("private"):
        raise RuntimeError("Refusing backup to public repo")
    f=recovery_key()
    clear=snapshot()
    count=verify_database(clear)
    encrypted=f.encrypt(clear)
    day=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    path=f"daily/{day}.sqlite3.fernet"
    sha=None
    check=subprocess.run([GH_BIN,"api",f"repos/{REPO}/contents/{path}"],
                         capture_output=True,text=True,timeout=25)
    if check.returncode==0:sha=json.loads(check.stdout)["sha"]
    payload={"message":f"Encrypted Shared Brain daily backup {day}",
             "content":base64.b64encode(encrypted).decode("ascii")}
    if sha:payload["sha"]=sha
    gh(f"repos/{REPO}/contents/{path}",request=payload)
    remote=gh(f"repos/{REPO}/contents/{path}")
    blob=base64.b64decode(remote["content"])
    restored=f.decrypt(blob)
    remote_count=verify_database(restored)
    if hashlib.sha256(clear).digest()!=hashlib.sha256(restored).digest():
        raise RuntimeError("Remote restore hash mismatch")
    if remote_count!=count:
        raise RuntimeError("Remote restore row count mismatch")
    print(json.dumps({"private_backup_repo":REPO,"day":day,
        "database_records":count,"remote_restore":"passed",
        "encrypted_bytes":len(blob),"key_offsite_copy":"required"},
        ensure_ascii=False))

if __name__=="__main__":main()

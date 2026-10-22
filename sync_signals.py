"""Record verified, minimal source signals without importing raw customer data.

Idempotent read-only probes; append a source-backed checkpoint only when the
signal changes. Never mark an entire project 'done' from a healthy service.
"""
import hashlib
import json
import os
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from gdn_brain import add_checkpoint,get_project,DEFAULT_DB

BASE=Path(os.environ.get("GDN_BRAIN_SOURCE_ROOT",str(Path.home()/"projects")))
STATE=Path(DEFAULT_DB).parent/"source_probe_state.json"
JACK=Path.home()/".hermes/profiles/kisa-lab/venture/100btc"

def signals():
    out=[]
    lead=BASE/"jdn-leadscout/data/gdn_latest_readonly_scan.json"
    if lead.is_file():
        try:
            data=json.loads(lead.read_text())
            n=int(data.get("sources_attempted",0))
            k=len(data.get("candidates",[]))
            errors=int(data.get("errors",0)) if not isinstance(data.get("errors"),list) else len(data["errors"])
            out.append(("gdn-lead-discovery","telegram-scan",
                f"Telegram scan: {n} sources, {k} candidates, {errors} errors",
                "vps:jdn-leadscout/data/gdn_latest_readonly_scan.json",
                str(lead.stat().st_mtime_ns)))
        except (ValueError,TypeError,KeyError,json.JSONDecodeError):
            pass
    # Count evidence, not the content of scanned conversations.
    digest=JACK/"digests/digest-cron.log"
    if digest.is_file():
        try:
            lines=digest.read_text(errors="replace").splitlines()
            valid=[x for x in lines if x.startswith("DIGEST_READY ")]
            if valid:
                row=json.loads(valid[-1][len("DIGEST_READY "):])
                n=int(row.get("count",0))
                out.append(("jack-startup-scout","daily-digest",
                    f"Jack daily discovery digest: {n} signals, date {row.get('date','unknown')}",
                    "vps:100btc/digests/digest-cron.log",
                    f"{row.get('date')}:{n}"))
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            pass
    white=BASE/"gdn-whiteboard"
    if white.is_dir():
        pilot=len(list((white/"jobs").glob("*/result.mp4")))
        tg=len(list((white/"telegram_jobs").glob("*/result.mp4")))
        jobs=len(list((white/"telegram_jobs").glob("*/request.json")))
        out.append(("gdn-whiteboard","render-artifacts",
            f"Whiteboard render artifacts: {pilot} local pilot MP4, {tg} Telegram MP4, {jobs} Telegram requests",
            "vps:gdn-whiteboard/jobs-and-telegram_jobs",
            f"pilot={pilot},telegram={tg},requests={jobs}"))
    for project,service in (("gdn-shared-brain","gdn-shared-brain-mcp"),
                            ("gdn-whiteboard","gdn-whiteboard-worker"),
                            ("jack-100btc-platform","100btc-control-center")):
        try:
            r=subprocess.run(["systemctl","is-active",service+".service"],
                             text=True,capture_output=True,timeout=4)
            state=r.stdout.strip()
            if state not in ("active","inactive","failed","activating","deactivating"):
                state="unknown"
            out.append((project,"service-"+service,
                f"systemd {service}.service is {state}",
                "vps:systemd/"+service,state))
        except (OSError,subprocess.TimeoutExpired):pass
    return out

def main():
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    history=json.loads(STATE.read_text()) if STATE.exists() else {}
    total=changed=0
    for pid,kind,detail,source,signature in signals():
        total+=1
        if not get_project(id=pid):continue
        key=pid+":"+kind
        digest=hashlib.sha256((source+"|"+signature).encode()).hexdigest()
        if history.get(key)==digest:continue
        add_checkpoint(id=pid,kind="test",actor="source-signal-sync",
            source_ref=source,evidence="verified",detail=detail)
        history[key]=digest
        changed+=1
    tmp=STATE.with_name(STATE.name+".tmp")
    tmp.write_text(json.dumps(history,sort_keys=True))
    os.chmod(tmp,0o600)
    os.replace(tmp,STATE)
    print(json.dumps({"sources_checked":total,"new_checkpoints":changed},ensure_ascii=False))

if __name__=="__main__":main()

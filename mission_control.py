"""Render a private, mobile-first, read-only project dashboard from Shared Brain.

Write under a protected web root (for example existing JDN Office BasicAuth).
Never publish this output to the public source code repository.
"""
from __future__ import annotations
import argparse
import html
import json
import os
import pathlib
from pathlib import Path
import tempfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from gdn_brain import list_projects,get_project
from brain_tasks import list_tasks

STATUS={
 "active":("В работе","active"),"blocked":("Блокировка","blocked"),
 "paused":("Пауза","paused"),"needs_review":("Проверить","review"),
 "idea":("В планах","idea"),"done":("Готово","done"),
 "archived":("Архив","archived")
}
def load_project_links():
    """Optional private per-installation links; never store user-specific URLs in public source."""
    loc=Path(os.environ.get("GDN_MISSION_LINKS","~/.config/gdn-shared-brain/mission-links.json")).expanduser()
    if not loc.is_file():return {}
    data=json.loads(loc.read_text())
    if not isinstance(data,dict):return {}
    return data

LINKS=load_project_links()

GROUP_HINTS=("jack-100BTC-","jack-EXPERIMENT-","hermes-default-","hermes-kisa-lab-","hermes-hermes-expert-")
PREF=("gdn-shared-brain","gdn-lead-discovery","provideoservis","hermes-routing","jack-startup-scout",
      "gdn-whiteboard","jdn-sitedoctor","gdn-lab-bot","jdn-office","jdn-reviewfix","jdn-listening")

def esc(value):
    return html.escape(str(value or ""),quote=True)

def category(p):
    return "research" if p["id"].startswith(GROUP_HINTS) else "portfolio"

def link_button(pid):
    values=[]
    for label,url in LINKS.get(pid,[]):
        u=urlparse(url)
        if u.scheme=="https" and u.netloc:
            values.append('<a class="extern" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>')
    return " ".join(values)

def task_html(t):
    label={"user":"Тебе","agent":"AI-агент","external":"Внешний"}[t["owner"]]
    st={"todo":"Далее","in_progress":"В работе","blocked":"Блокировка","done":"Готово","canceled":"Отменено"}[t["status"]]
    return '<div class="task"><span class="mini">'+esc(label)+' · '+esc(st)+'</span><span>'+esc(t["title"])+'</span></div>'

def card(p,tasks):
    status,css=STATUS.get(p["status"],("Неизвестно","review"))
    ts=p["updated_at"][:16].replace("T"," ")
    open_tasks=[t for t in tasks if t["status"] not in ("done","canceled")]
    known=get_project(id=p["id"])
    latest=next((e for e in (known or {}).get("events",[]) if e["evidence"]=="verified"),None)
    proof=('<span class="proof">Есть подтверждённая запись · '+esc(latest["created_at"][:10])+'</span>'
           if latest else '<span class="uncertain">Статус требует подтверждения</span>')
    if p["status"] in ("needs_review","idea","paused"):proof='<span class="uncertain">По реестру · не проверено как работающее</span>'
    command="Открой GDN Shared Brain, проект "+p["id"]+". Прочитай карточку, задачи и последние контрольные точки. Проверь актуальное состояние, продолжи следующий шаг и сохрани результат."
    attrs=esc(command)
    innertasks="".join(task_html(t) for t in open_tasks[:8]) or '<p class="muted">Нет записанных незавершённых задач.</p>'
    return f'''<details class="project-card" data-category="{category(p)}" data-status="{esc(p["status"])}" data-query="{esc((p["name"]+" "+p["summary"]+" "+p["next_action"]).lower())}">
<summary><span class="project-heading"><span class="kind">{esc(p["priority"].upper())} · {esc(p["id"])}</span>
<span class="project-name">{esc(p["name"])}</span></span><span class="status {css}">{status}</span>
<span class="project-note">{esc(p["next_action"] or p["summary"][:150])}</span></summary>
<div class="project-body"><p>{esc(p["summary"])}</p><div class="body-heading">Что дальше</div>
<p>{esc(p["next_action"] or "Следующий шаг пока не определён")}</p>
<div class="body-heading">Задачи</div><div class="task-list">{innertasks}</div>
<div class="footline">{proof}<span>Карточка: {esc(ts)} UTC</span></div>
<div class="actions"><button class="copy" data-copy="{attrs}">Скопировать команду</button>{link_button(p["id"])}</div></div></details>'''

def render():
    projects=list_projects()
    all_tasks=list_tasks()
    byproject=defaultdict(list)
    for t in all_tasks:byproject[t["project_id"]].append(t)
    cores=sorted((p for p in projects if category(p)=="portfolio"),
                 key=lambda p:(int(p["priority"][1]),PREF.index(p["id"]) if p["id"] in PREF else 200,p["name"].lower()))
    research=sorted((p for p in projects if category(p)=="research"),key=lambda p:p["name"].lower())
    active=Counter(p["status"] for p in cores)
    active_task=[t for t in all_tasks if t["status"] not in ("done","canceled")]
    mine=sorted((t for t in active_task if t["owner"]=="user"),key=lambda t:(t["priority"],t["title"]))
    agent=sorted((t for t in active_task if t["owner"]=="agent"),key=lambda t:(t["priority"],t["title"]))
    readable=datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d.%m.%Y · %H:%M")
    archive='<div class="empty" id="empty" hidden>По этим условиям проекты не найдены.</div>'
    def queue(tasks):
        return "".join('<div class="qitem"><span class="qproject">'+esc(next((p["name"] for p in projects if p["id"]==t["project_id"]),t["project_id"]))+'</span><div>'+esc(t["title"])+'</div></div>' for t in tasks[:6]) or '<span class="muted">Нет назначенных задач.</span>'
    page='''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#10161b"><meta name="robots" content="noindex,nofollow,noarchive">
<title>GDN Mission Control — проекты</title>
<style>
:root{color-scheme:dark;--bg:#10161b;--panel:#1a232a;--sub:#222e34;--line:#35424a;--text:#ecf4f2;--muted:#a0b1b7;--mint:#87d8c2;--amber:#efba77;--pink:#e4a3a9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.52 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--mint);text-decoration:none}button,input{font:inherit}button{cursor:pointer}
.shell{max-width:1020px;margin:auto;padding:20px 18px 95px}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.brand{font-size:12px;font-weight:800;letter-spacing:.13em;color:var(--mint)}
.top a{font-size:13px;color:var(--muted)}h1{font-size:clamp(30px,6vw,49px);line-height:1.1;letter-spacing:-.055em;margin:26px 0 8px}
.lead{max-width:680px;color:var(--muted);margin:0 0 15px}
.stamp{color:var(--muted);font-size:12px;margin-bottom:24px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0 28px}
.metric{background:var(--panel);padding:16px 13px;border:1px solid var(--line);border-radius:13px}
.metric b{font-size:25px;display:block;letter-spacing:-.04em}.metric span{color:var(--muted);font-size:12px}
.section-head{display:flex;align-items:center;gap:10px;margin:25px 0 12px}h2{font-size:19px;letter-spacing:-.025em;margin:0}.section-head small{margin-left:auto;color:var(--muted)}
.queues{display:grid;grid-template-columns:1fr 1fr;gap:12px}.queue{border:1px solid var(--line);background:var(--panel);border-radius:16px;padding:16px}
.qitem{padding:11px 0;border-bottom:1px solid var(--line)}.qitem:last-child{border:0}.qproject{font-size:11px;color:var(--mint);display:block;margin-bottom:3px}
.filters{display:flex;gap:8px;overflow-x:auto;padding:3px 0 10px;scrollbar-width:none}.filter{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:9px 12px;white-space:nowrap}
.filter.selected{background:#284b45;color:var(--text);border-color:#4d8276}
.search{background:var(--panel);border:1px solid var(--line);border-radius:11px;color:var(--text);outline:none;padding:12px 14px;width:100%;margin:10px 0 8px}
.cards{display:grid;gap:10px}.project-card{border-radius:14px;background:var(--panel);border:1px solid var(--line);overflow:hidden}
.project-card[open]{border-color:#63837f}.project-card summary{position:relative;padding:15px 16px 15px;display:grid;grid-template-columns:1fr auto;gap:6px 14px;cursor:pointer;list-style:none}
.project-card summary::-webkit-details-marker{display:none}.project-heading{display:flex;flex-direction:column;min-width:0}
.kind{font:700 10px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.045em;color:var(--muted);overflow-wrap:anywhere}
.project-name{font-weight:750;font-size:17px;letter-spacing:-.02em}
.project-note{color:#bac9cd;font-size:13px;grid-column:1/-1;max-width:840px}
.status{font-size:11px;border:1px solid var(--line);border-radius:999px;padding:4px 9px;align-self:start;white-space:nowrap}
.status.active{color:var(--mint);border-color:#3e7b70}.status.blocked{color:var(--pink);border-color:#795159}.status.paused{color:var(--amber);border-color:#786042}
.status.review,.status.idea{color:var(--muted)}.status.done{color:var(--mint)}
.project-body{border-top:1px solid var(--line);padding:17px 16px;color:#c6d4d6}.project-body p{margin:0 0 12px}
.body-heading{font-size:11px;letter-spacing:.07em;color:var(--mint);text-transform:uppercase;font-weight:700;margin:16px 0 5px}
.task{display:flex;gap:9px;flex-direction:column;background:var(--sub);border-radius:10px;padding:9px 11px;margin:6px 0}
.mini{font-size:11px;color:var(--amber)}.muted{color:var(--muted)}
.footline{border-top:1px solid var(--line);margin-top:15px;padding-top:13px;display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;font-size:11px;color:var(--muted)}
.proof{color:var(--mint)}.uncertain{color:var(--amber)}
.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px}.copy,.extern{border:1px solid #588c7f;border-radius:10px;color:var(--mint);background:#214039;padding:9px 13px;font-size:13px}
.extern{background:transparent}.empty{padding:24px;color:var(--muted);text-align:center}
.note{font-size:12px;color:var(--muted);line-height:1.5;margin-top:22px;border-top:1px solid var(--line);padding-top:18px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:34px}
@media(max-width:650px){.shell{padding:16px 13px 88px}.metrics{grid-template-columns:repeat(2,1fr)}.queues{grid-template-columns:1fr}.metric b{font-size:24px}}
@media(prefers-reduced-motion:no-preference){.project-card{transition:border-color .2s}}
</style></head>
<body><div class="shell">
<div class="top"><div class="brand">GDN / MISSION CONTROL</div><a href="/">← JDN Office</a></div>
<h1>Все проекты.<br>Один пульт.</h1>
<p class="lead">Что работает, что остановилось и какие действия нужны дальше. Общая база доступна Hermes и другим подключённым AI-агентам.</p>
<div class="stamp">Снимок: %%TIMESTAMP%% (Самуи) · Отчёт формируется с VPS</div>
<div class="metrics">
<div class="metric"><b>%%COUNT%%</b><span>Основных проектов</span></div>
<div class="metric"><b>%%ACTIVE%%</b><span>В работе</span></div>
<div class="metric"><b>%%BLOCKED%%</b><span>Блокировки</span></div>
<div class="metric"><b>%%RESEARCH%%</b><span>Записей Jack/Hermes</span></div></div>
<div class="section-head"><h2>Следующие действия</h2><small>По исполнителям</small></div>
<div class="queues"><div class="queue"><h2>Нужно от тебя</h2>%%USER_QUEUE%%</div>
<div class="queue"><h2>Работа AI-агентов</h2>%%AGENT_QUEUE%%</div></div>
<div class="section-head"><h2>Реестр</h2><small>Нажми карточку для подробностей</small></div>
<div class="filters">
<button class="filter selected" data-status="all">Основные (%%COUNT%%)</button>
<button class="filter" data-status="active">В работе</button>
<button class="filter" data-status="blocked">Блокировки</button>
<button class="filter" data-status="needs_review">Проверить</button>
<button class="filter" data-status="paused">Пауза</button>
<button class="filter" data-status="research">Архив идей (%%RESEARCH%%)</button>
</div>
<input class="search" id="search" type="search" placeholder="Найти проект или задачу" aria-label="Поиск проектов">
<div class="cards" id="cards">%%CARDS%%</div>%%EMPTY%%
<p class="note">Статусы «Проверить» означают, что код или карточка проекта обнаружены, но работоспособность ещё не подтверждена. Изменения исходных систем синхронизируются отдельно. Пароли и API-ключи в этот реестр не записываются. Grok временно на паузе по твоему решению.</p>
<footer>GDN Shared Brain · Приватный JDN Office · <a href="/mission/">Обновить пульт</a></footer>
</div>
<script>
const cards=[...document.querySelectorAll(".project-card")];
const filters=[...document.querySelectorAll("[data-status]")];
const input=document.getElementById("search");
const empty=document.getElementById("empty");
let current="all";
function show(){
 const q=(input.value||"").trim().toLocaleLowerCase("ru-RU");
 let visible=0;
 for(const card of cards){
   const isResearch=card.dataset.category==="research";
   const ok=current==="research"?isResearch:(!isResearch&&(current==="all"||card.dataset.status===current));
   const match=!q||card.dataset.query.includes(q);
   card.hidden=!(ok&&match);
   if(!card.hidden)visible++;
 }
 empty.hidden=visible!==0;
}
filters.forEach(el=>el.addEventListener("click",()=>{
 current=el.dataset.status;
 filters.forEach(f=>f.classList.toggle("selected",f===el));
 show();
}));
input.addEventListener("input",show);
document.querySelectorAll("[data-copy]").forEach(btn=>{
 btn.addEventListener("click",async()=>{
   const cmd=btn.dataset.copy;
   try{await navigator.clipboard.writeText(cmd);btn.textContent="Скопировано";setTimeout(()=>btn.textContent="Скопировать команду",1600)}
   catch(e){window.prompt("Скопируйте команду:",cmd)}
 });
});
show();
</script></body></html>'''
    replacements={
      "%%TIMESTAMP%%":esc(readable),"%%COUNT%%":str(len(cores)),
      "%%ACTIVE%%":str(active["active"]),"%%BLOCKED%%":str(active["blocked"]),
      "%%RESEARCH%%":str(len(research)),
      "%%USER_QUEUE%%":queue(mine),"%%AGENT_QUEUE%%":queue(agent),
      "%%CARDS%%":"".join(card(p,byproject[p["id"]]) for p in cores+research),
      "%%EMPTY%%":archive
    }
    for needle,value in replacements.items():page=page.replace(needle,value)
    return page

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--out",required=True)
    args=arg.parse_args()
    out=pathlib.Path(args.out).expanduser()
    out.parent.mkdir(parents=True,exist_ok=True)
    page=render()
    with tempfile.NamedTemporaryFile("w",dir=out.parent,prefix=".mission-",suffix=".html",delete=False,encoding="utf-8") as f:
        temp=pathlib.Path(f.name);f.write(page)
    os.chmod(temp,0o644)
    os.replace(temp,out)
    print(json.dumps({"output":str(out),"bytes":out.stat().st_size,"projects":len(list_projects())}))
if __name__=="__main__":main()

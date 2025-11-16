#!/usr/bin/env python3
"""
controller.py - full stable controller for Hot-Plug Heaven
Features:
 - threaded Flask server (fast /request)
 - background allocation scheduler (conservative stealing)
 - SQLite persistent logs
 - dashboard (core grid, pending queue, allocations, live jobs, activity)
"""
from flask import Flask, request, jsonify, render_template_string
import threading, time, sqlite3, socket
import requests

app = Flask(__name__)

# ---------- Runtime data structures ----------
AGENTS = {}            # agent_name -> {total_cores, endpoint, last, offset}
CORE_MAP = {}          # global_core_index -> (agent_name, job) or None
ALLOCATIONS = {}       # (agent_name, job) -> [global_core_indices]
JOB_REQUEST = {}       # (agent_name, job) -> originally_requested_cores
PENDING = []           # queued requests (dicts: vm, job, pid, need, ts)
ACTIVITY_LOG = []      # in-memory activity log (latest first)

LOCK = threading.RLock()

# ---------- Config / tuning ----------
LOG_DB = "alloc_log.db"
SCHED_INTERVAL = 1.0          # scheduler loop interval (seconds)
REQUEST_TIMEOUT = 6           # timeout calling agents
MIN_CORES_PER_JOB = 1
RESERVE_BUFFER = 0            # keep zero reserve for conservative behavior

# ---------- Utility functions ----------
def log_db(action, detail):
    try:
        conn = sqlite3.connect(LOG_DB, timeout=5)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS log(ts TEXT, action TEXT, detail TEXT)")
        c.execute("INSERT INTO log VALUES(datetime('now'), ?, ?)", (action, detail))
        conn.commit(); conn.close()
    except Exception:
        pass

def push_activity(s):
    ts = time.strftime("%H:%M:%S")
    with LOCK:
        ACTIVITY_LOG.insert(0, f"[{ts}] {s}")
        if len(ACTIVITY_LOG) > 400:
            ACTIVITY_LOG.pop()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# ---------- Flask endpoints ----------
@app.route("/")
def index():
    html = """<!doctype html><html><head><meta charset="utf-8"><title>Hot-Plug Heaven</title>
    <style>
      body{font-family:Inter,Arial,Helvetica,sans-serif;padding:12px;background:#f6f7fb;color:#111}
      .container{display:flex;gap:12px;flex-wrap:wrap}
      .card{background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 6px rgba(0,0,0,0.06)}
      .cores{display:flex;flex-wrap:wrap;gap:8px}
      .core{width:88px;height:56px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600}
      .free{background:#97d6a9;color:#02350f}
      .agentA{background:#6ea8fe}
      .agentB{background:#f2a365}
      pre{background:#f7f8fa;padding:8px;border-radius:6px;max-height:260px;overflow:auto}
    </style></head><body>
    <h2>Hot-Plug Heaven — Controller</h2>
    <div style="margin-bottom:8px">Controller IP: {{ip}} | Scheduler interval: {{interval}}s</div>
    
    <div class="container">
      <div style="flex:1" class="card">
        <div style="font-size:14px;margin-bottom:6px">Global core map</div>
        <div id="coregrid" class="cores"></div>
      </div>
      <div style="width:420px" class="card">
        <div style="font-size:14px;margin-bottom:6px">Pending queue (FIFO)</div>
        <pre id="pending">loading...</pre>
        <div style="font-size:14px;margin-top:8px">Activity log</div>
        <pre id="act">loading...</pre>
      </div>
    </div>

    <div class="container" style="margin-top:12px">
      <div style="flex:1" class="card">
        <div style="font-size:14px;margin-bottom:6px">Allocations</div>
        <pre id="alloc">loading...</pre>
      </div>
      <div style="flex:1" class="card">
        <div style="font-size:14px;margin-bottom:6px">Live jobs (per agent)</div>
        <pre id="live">loading...</pre>
      </div>
    </div>

    <script>
    async function refresh(){
      try{
        const r = await fetch('/summary'); const j = await r.json();
        // coregrid
        const coregrid = document.getElementById('coregrid'); coregrid.innerHTML='';
        const cm = j.core_map;
        const keys = Object.keys(cm).map(x=>parseInt(x)).sort((a,b)=>a-b);
        keys.forEach(k=>{
          const v = cm[k];
          const el = document.createElement('div'); el.className='core';
          if(!v){ el.className += ' free'; el.innerText='core '+k; }
          else { el.className += (v[0]==='agentA'?' agentA':' agentB'); el.innerText = v[0]+'\\n#'+k; el.title=v[1]; }
          coregrid.appendChild(el);
        });
        document.getElementById('pending').innerText = JSON.stringify(j.pending, null, 2);
        document.getElementById('act').innerText = j.activity.join("\\n");
        document.getElementById('alloc').innerText = JSON.stringify(j.allocations, null, 2);
        let liveTxt = '';
        for(const a of Object.keys(j.live_jobs)){
          liveTxt += '== ' + a + ' ==\\n';
          j.live_jobs[a].forEach(x=> {
            liveTxt += `${x.job} pid:${x.pid} cores:${JSON.stringify(x.cores)} cpu:${x.cpu_percent}%\\n`;
          });
          liveTxt += '\\n';
        }
        document.getElementById('live').innerText = liveTxt;
      } catch(e){ console.error(e); }
    }
    setInterval(refresh, 5000);
    refresh();
    </script>
    </body></html>"""
    return render_template_string(html, ip=get_local_ip(), interval=SCHED_INTERVAL)

@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    agent = data.get("vm_name")
    endpoint = data.get("endpoint")
    total = int(data.get("total_cores", 1))
    offset = int(data.get("core_offset", 0))
    with LOCK:
        AGENTS[agent] = {"total_cores": total, "endpoint": endpoint, "last": time.time(), "offset": offset}
        for g in range(offset, offset+total):
            CORE_MAP.setdefault(g, None)
    push_activity(f"registered {agent} offset={offset} cores={total}")
    log_db("register", f"{agent} registered offset={offset} cores={total}")
    return jsonify({"ok": True})

@app.route("/request", methods=["POST"])
def request_alloc():
    data = request.json or {}
    vm = data.get("vm"); job = data.get("job"); pid = int(data.get("pid")); need = int(data.get("cores_requested",1))
    entry = {"vm": vm, "job": job, "pid": pid, "need": need, "ts": time.time()}
    with LOCK:
        if vm not in AGENTS:
            return jsonify({"status":"error","message":"unknown agent"}),400
        PENDING.append(entry)
        JOB_REQUEST[(vm, job)] = need
        push_activity(f"queued request {job}@{vm} need={need}")
        log_db("queue", f"{vm}/{job} need={need}")
    return jsonify({"status":"queued"})

@app.route("/complete", methods=["POST"])
def complete():
    data = request.json or {}
    vm = data.get("vm"); job = data.get("job")
    with LOCK:
        key = (vm, job)
        if key not in ALLOCATIONS:
            return jsonify({"ok": False, "message":"not allocated"}), 400
        cores = ALLOCATIONS.pop(key)
        try:
            requests.post(AGENTS[vm]["endpoint"]+"/release", json={"job": job, "keep_cores":[]}, timeout=REQUEST_TIMEOUT)
        except Exception: pass
        for c in cores:
            CORE_MAP[c] = None
        JOB_REQUEST.pop(key, None)
        push_activity(f"completed {job}@{vm}, freed {cores}")
        log_db("complete", f"{vm}/{job} freed {cores}")
    return jsonify({"ok": True, "freed": cores})

@app.route("/summary")
def summary():
    with LOCK:
        agents_copy = {k: {"total_cores": v["total_cores"], "offset": v["offset"], "endpoint": v["endpoint"]} for k,v in AGENTS.items()}
        core_map_copy = {str(k): v for k,v in CORE_MAP.items()}
        alloc_copy = {f"{a}|{j}": cores for (a,j),cores in ALLOCATIONS.items()}
        pending_copy = list(PENDING)
        activity_copy = list(ACTIVITY_LOG)[:200]
    live_jobs = {}
    for a in agents_copy.keys():
        try:
            r = requests.get(AGENTS[a]["endpoint"]+"/status", timeout=REQUEST_TIMEOUT).json()
            live_jobs[a] = r.get("jobs",[])
        except Exception:
            live_jobs[a] = []
    return jsonify({"agents":agents_copy,"core_map":core_map_copy,"allocations":alloc_copy,"pending":pending_copy,"activity":activity_copy,"live_jobs":live_jobs})

# ---------- Scheduler + allocation ----------
def estimate_used_cores(cpu_percent, allocated):
    est = max(1,int(round((cpu_percent/100.0)*allocated)))
    return min(est, allocated)

def _assign_and_record(agent, job, pid, cores):
    try:
        r = requests.post(AGENTS[agent]["endpoint"]+"/allocate", json={"job":job,"pid":pid,"cores":cores}, timeout=REQUEST_TIMEOUT)
        if r.status_code==200 and r.json().get("ok"):
            for c in cores:
                CORE_MAP[c] = (agent, job)
            ALLOCATIONS[(agent, job)] = ALLOCATIONS.get((agent, job),[]) + cores
            JOB_REQUEST[(agent, job)] = JOB_REQUEST.get((agent, job), len(cores))
            log_db("assign", f"{agent}/{job} -> {cores}")
            return True
    except Exception as e:
        print("assign failed", e)
    return False

def scheduler_loop():
    while True:
        with LOCK:
            if not PENDING: pass
            for req in list(PENDING):
                vm = req["vm"]; job=req["job"]; pid=req["pid"]; need=req["need"]
                if vm not in AGENTS:
                    push_activity(f"drop request {job}@{vm} (unknown agent)")
                    log_db("drop", f"{job}@{vm}")
                    PENDING.remove(req)
                    continue
                offset,total=AGENTS[vm]["offset"],AGENTS[vm]["total_cores"]
                agent_slots = list(range(offset, offset+total))
                free_slots = [g for g in agent_slots if CORE_MAP.get(g) is None]
                if len(free_slots) >= need + RESERVE_BUFFER:
                    pick = free_slots[:need]
                    if _assign_and_record(vm, job, pid, pick):
                        push_activity(f"allocated {job}@{vm} -> {pick}")
                        PENDING.remove(req)
                        continue
                # conservative steal
                candidates=[]
                for a_name,info in AGENTS.items():
                    try:
                        resp=requests.get(info["endpoint"]+"/status", timeout=REQUEST_TIMEOUT).json()
                        for j in resp.get("jobs",[]):
                            allocated = len([g for g,m in CORE_MAP.items() if m==(a_name,j["job"])])
                            if allocated<=MIN_CORES_PER_JOB: continue
                            cpu_p=float(j.get("cpu_percent",0.0))
                            used=estimate_used_cores(cpu_p, allocated)
                            spare=allocated-used
                            if spare>=1 and (allocated-1)>=MIN_CORES_PER_JOB:
                                idxs=[g for g,m in CORE_MAP.items() if m==(a_name,j["job"])]
                                candidates.append({"spare":spare,"agent":a_name,"job":j["job"],"idxs":idxs})
                    except Exception: continue
                candidates.sort(key=lambda x:x["spare"], reverse=True)
                need_remaining = need - len(free_slots)
                stolen_indices=[]
                while need_remaining>0 and candidates:
                    c=candidates.pop(0)
                    chosen=[c["idxs"][-1]]
                    stolen_indices.append({"src_agent":c["agent"],"src_job":c["job"],"idxs":chosen})
                    need_remaining-=len(chosen)
                if need_remaining<=0 and stolen_indices:
                    for s in stolen_indices:
                        try:
                            r=requests.get(AGENTS[s["src_agent"]]["endpoint"]+"/status", timeout=REQUEST_TIMEOUT).json()
                            current=[]
                            for jj in r.get("jobs",[]):
                                if jj["job"]==s["src_job"]: current=jj.get("cores",[])
                            new_cores=[c for c in current if c not in s["idxs"]]
                            requests.post(AGENTS[s["src_agent"]]["endpoint"]+"/release", json={"job":s["src_job"],"keep_cores":new_cores}, timeout=REQUEST_TIMEOUT)
                            for g in s["idxs"]: CORE_MAP[g]=None
                            push_activity(f"stole {s['idxs']} from {s['src_job']}@{s['src_agent']} for {job}@{vm}")
                            log_db("steal", f"stole {s['idxs']} from {s['src_job']}@{s['src_agent']} for {job}@{vm}")
                        except Exception: pass
                    free_slots=[g for g in agent_slots if CORE_MAP.get(g) is None]
                    pick=free_slots[:need]
                    if len(pick)==need and _assign_and_record(vm,job,pid,pick):
                        push_activity(f"allocated {job}@{vm} -> {pick} (after steal)")
                        PENDING.remove(req)
                        continue
        time.sleep(SCHED_INTERVAL)

def start_scheduler():
    t=threading.Thread(target=scheduler_loop,daemon=True)
    t.start()

# ---------- Main ----------
if __name__=="__main__":
    ip=get_local_ip()
    print("Controller starting on", ip, "port 5000")
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, threaded=True)

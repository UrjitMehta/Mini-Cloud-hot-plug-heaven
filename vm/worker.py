#!/usr/bin/env python3
"""
worker.py - concurrent token-start worker
- Spawns CPU tasks that wait for a "start token" file.
- Requests allocation from controller using PID.
- If allocated, releases the start token so child begins CPU work.
- If queued, polls /summary until allocation, then releases token.
- Each job runs concurrently in its own thread.
- On process exit sends /complete to controller.
"""

import json
import subprocess
import time
import os
import pathlib
import requests
import sys
import threading
import random
from typing import Dict

START_DIR = "/tmp/hotplug_starts"
os.makedirs(START_DIR, exist_ok=True)

POLL_INTERVAL = 1.5
REQUEST_TIMEOUT = 30
ALLOC_WAIT_TIMEOUT = 180

def spawn_waiting_child(duration: int) -> int:
    """Spawn a Python child that waits for a token file before running CPU task."""
    code = f"""
import os, time
token='{START_DIR}/start_' + str(os.getpid())
while not os.path.exists(token):
    time.sleep(0.25)
end=time.time()+{int(duration)}
x=0
while time.time()<end:
    for i in range(100000):
        x += i*i
    time.sleep(0.01)
"""
    p = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
    return p.pid

def controller_summary(controller_url: str) -> Dict:
    try:
        r = requests.get(controller_url.rstrip("/") + "/summary", timeout=10)
        return r.json()
    except Exception:
        return {}

def is_job_allocated_in_summary(summary: Dict, agent: str, job_name: str):
    key = f"{agent}|{job_name}"
    return key in summary.get("allocations", {})

def release_start_token(pid: int):
    token = f"{START_DIR}/start_{pid}"
    try:
        pathlib.Path(token).write_text("start")
    except Exception:
        pass

def remove_start_token(pid: int):
    token = f"{START_DIR}/start_{pid}"
    try:
        os.remove(token)
    except Exception:
        pass

def load_jobs_and_select_version() -> list:
    """Selects a random job version from the available options."""
    with open('jobs.json') as f:
        jobs_data = json.load(f)
        job_version = random.choice(jobs_data["versions"])  # Randomly select version
        print(f"Selected Job Version: {job_version['version']}")  # Print the selected version
        return job_version["jobs"]

def run_job_cycle(controller: str, job: Dict):
    name = job.get("name")
    agent = job.get("agent")
    need = int(job.get("cores", 1))
    duration = int(job.get("duration", 60))

    print(f"Spawning {name} (needs {need} cores, dur {duration}s) for agent {agent} ...")
    pid = spawn_waiting_child(duration)
    remove_start_token(pid)

    req_payload = {"vm": agent, "job": name, "pid": pid, "cores_requested": need}
    try:
        r = requests.post(controller.rstrip("/") + "/request", json=req_payload, timeout=REQUEST_TIMEOUT)
        resp = r.json() if r else {}
    except Exception as e:
        print(f"Request failed for {name} pid {pid}: {e}")
        _wait_and_notify_on_failure(controller, agent, name, pid)
        return

    status = resp.get("status")
    if status in ("allocated", "stolen_allocated"):
        print(f"Controller resp allocated {resp.get('cores',[])} for {name}")
        release_start_token(pid)
    else:
        print(f"{name} queued. Polling summary for allocation...")
        start_t = time.time()
        allocated = False
        while time.time() - start_t < ALLOC_WAIT_TIMEOUT:
            summary = controller_summary(controller)
            if is_job_allocated_in_summary(summary, agent, name):
                allocated = True
                print(f"{name} got allocated. Releasing start token.")
                release_start_token(pid)
                break
            try:
                ret = os.waitpid(pid, os.WNOHANG)[0]
                if ret != 0:
                    print(f"{name} (pid {pid}) ended before allocation.")
                    try:
                        requests.post(controller.rstrip("/") + "/complete",
                                      json={"vm": agent, "job": name, "pid": pid}, timeout=10)
                    except Exception:
                        pass
                    return
            except ChildProcessError:
                pass
            time.sleep(POLL_INTERVAL)
        if not allocated:
            print(f"Timed out waiting for allocation for {name} pid {pid}. Cleaning up child.")
            try:
                os.kill(pid, 9)
            except Exception:
                pass
            try:
                requests.post(controller.rstrip("/") + "/complete",
                              json={"vm": agent, "job": name, "pid": pid}, timeout=10)
            except Exception:
                pass
            return

    print(f"{name} is running (pid {pid}) ... waiting for completion.")
    try:
        while True:
            ret = os.waitpid(pid, os.WNOHANG)[0]
            if ret != 0:
                break
            time.sleep(1)
    except ChildProcessError:
        pass

    print(f"{name} (pid {pid}) finished; notifying controller ...")
    try:
        requests.post(controller.rstrip("/") + "/complete",
                      json={"vm": agent, "job": name, "pid": pid}, timeout=10)
        print(f"Reported completion {name}")
    except Exception as e:
        print(f"Complete notify failed for {name}: {e}")
    finally:
        remove_start_token(pid)

def _wait_and_notify_on_failure(controller: str, agent: str, name: str, pid: int):
    grace = 8
    t0 = time.time()
    while time.time() - t0 < grace:
        try:
            ret = os.waitpid(pid, os.WNOHANG)[0]
            if ret != 0:
                break
        except ChildProcessError:
            break
        time.sleep(0.5)
    try:
        os.kill(pid, 9)
    except Exception:
        pass
    try:
        requests.post(controller.rstrip("/") + "/complete",
                      json={"vm": agent, "job": name, "pid": pid}, timeout=6)
    except Exception:
        pass

def main():
    if not os.path.exists('jobs.json'):
        print("jobs.json missing")
        sys.exit(1)

    controller = "http://192.168.29.200:5000"  # Use your actual controller URL
    jobs = load_jobs_and_select_version()  # Load and select random job version

    threads = []
    for job in jobs:
        t = threading.Thread(target=run_job_cycle, args=(controller, job), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.1)  # small stagger to avoid bursting controller

    # Wait for all threads to complete
    for t in threads:
        t.join()

    print("All worker jobs processed.")

if __name__ == "__main__":
    main()
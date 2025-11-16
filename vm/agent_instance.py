#!/usr/bin/env python3
"""
agent_instance.py
Agent instance exposing /status, /allocate, /release.
"""
import argparse, socket, threading, os
from flask import Flask, request, jsonify
import psutil, requests, time

app = Flask(__name__)
parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--cores", type=int, required=True)
parser.add_argument("--offset", type=int, required=True)
parser.add_argument("--controller", required=True)
args = parser.parse_args()

AGENT_NAME = args.name
AGENT_PORT = args.port
TOTAL_CORES = args.cores
CORE_OFFSET = args.offset
CONTROLLER = args.controller.rstrip('/')
jobs = {}  # job -> {pid, cores}

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

@app.route("/status")
def status():
    rows = []
    for jname, jinfo in list(jobs.items()):
        pid = jinfo.get("pid")
        cores = jinfo.get("cores", [])
        cpu_percent = 0.0
        try:
            p = psutil.Process(pid)
            cpu_percent = p.cpu_percent(interval=0.1)
        except Exception:
            cpu_percent = 0.0
        rows.append({"job": jname, "pid": pid, "cores": cores, "cpu_percent": cpu_percent})
    return jsonify({"vm": AGENT_NAME, "total_cores": TOTAL_CORES, "offset": CORE_OFFSET, "jobs": rows})

@app.route("/allocate", methods=["POST"])
def allocate():
    payload = request.json or {}
    job = payload.get("job")
    pid = int(payload.get("pid"))
    cores = payload.get("cores", [])
    try:
        os.sched_setaffinity(pid, set(cores))
        jobs[job] = {"pid": pid, "cores": cores}
        return jsonify({"ok": True, "job": job, "cores": cores})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/release", methods=["POST"])
def release():
    payload = request.json or {}
    job = payload.get("job")
    keep = payload.get("keep_cores", [])
    if job not in jobs:
        return jsonify({"ok": False, "error": "job not found"}), 404
    pid = jobs[job]["pid"]
    try:
        os.sched_setaffinity(pid, set(keep))
        jobs[job]["cores"] = list(keep)
        return jsonify({"ok": True, "job": job, "cores": list(keep)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

def register_once():
    try:
        payload = {"vm_name": AGENT_NAME, "total_cores": TOTAL_CORES,
                   "endpoint": f"http://{get_local_ip()}:{AGENT_PORT}",
                   "core_offset": CORE_OFFSET}
        requests.post(CONTROLLER + "/register", json=payload, timeout=4)
    except Exception:
        pass

def heartbeat_loop():
    while True:
        try:
            requests.post(CONTROLLER + "/register", json={"vm_name": AGENT_NAME}, timeout=4)
        except Exception:
            pass
        time.sleep(10)

if __name__ == "__main__":
    print(f"Agent {AGENT_NAME} starting on port {AGENT_PORT}, cores {CORE_OFFSET}..{CORE_OFFSET+TOTAL_CORES-1}")
    register_once()
    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=AGENT_PORT)
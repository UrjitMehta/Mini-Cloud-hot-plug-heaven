#!/usr/bin/env bash
python3 - <<'PY'
import json, subprocess
cfg = json.load(open('agents.json'))
controller = cfg.get('controller','http://127.0.0.1:5000')
for a in cfg.get('agents', []):
    name=a['name']; port=a['port']; cores=a['cores']; offset=a['offset']
    cmd=f"python3 agent_instance.py --name {name} --port {port} --cores {cores} --offset {offset} --controller {controller}"
    print("Launching:", cmd)
    subprocess.Popen(cmd, shell=True, stdout=open(f"{name}.log","a"), stderr=open(f"{name}.err","a"))
print("Launched agents.")
PY
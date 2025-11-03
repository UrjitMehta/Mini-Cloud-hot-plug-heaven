import psutil
import time
import json
from datetime import datetime

LOG_FILE = "resource_log.json"

def get_metrics():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    return {"cpu": cpu, "memory": mem, "timestamp": datetime.now().isoformat()}

def log_metrics():
    while True:
        data = get_metrics()
        print(f"[{data['timestamp']}] CPU: {data['cpu']}% | MEM: {data['memory']}%")
        with open(LOG_FILE, "a") as f:
            json.dump(data, f)
            f.write("\n")
        time.sleep(5)  # every 5 seconds

if __name__ == "__main__":
    log_metrics()

import requests, time, random, logging, json
from colorama import Fore, Style, init

init(autoreset=True)

# =============================
# CONFIG
# =============================
VM_AGENT_URL = "http://127.0.0.1:5000/usage"  # VM Flask agent endpoint
DASHBOARD_URL = "http://127.0.0.1:5050/update"  # Dashboard Flask endpoint
PROCESSES = ["A", "B", "C"]
CHECK_INTERVAL = 2  # seconds
CPU_THRESHOLD_HIGH = 75
CPU_THRESHOLD_LOW = 25

# =============================
# STATE VARIABLES
# =============================
core_allocation = {}  # core_id -> owner
process_cores = {}    # process_name -> [core_ids]

# =============================
# LOGGING
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log(msg, color=None):
    if color:
        print(color + msg + Style.RESET_ALL)
    else:
        print(msg)

# =============================
# CORE MANAGEMENT
# =============================
def reallocate_core(core_id, new_owner):
    """Move a core to a new process or release it if no new owner."""
    prev_owner = core_allocation.get(core_id)
    if prev_owner and prev_owner in process_cores:
        if core_id in process_cores[prev_owner]:
            process_cores[prev_owner].remove(core_id)
        logging.info(f"Core {core_id} removed from {prev_owner}")

    if new_owner is None:
        core_allocation[core_id] = None
        logging.info(f"Core {core_id} released to pool (no reassignment)")
        return

    if core_allocation.get(core_id) == new_owner:
        return

    core_allocation[core_id] = new_owner
    if new_owner not in process_cores:
        process_cores[new_owner] = []
    if core_id not in process_cores[new_owner]:
        process_cores[new_owner].append(core_id)
    logging.info(f"Core {core_id} assigned to {new_owner}")


def log_allocation():
    """Print core and process allocation overview."""
    visual = []
    for cid, owner in core_allocation.items():
        status = owner if owner else "Idle"
        visual.append(f"Core{cid}:{status}")
    logging.info(" | ".join(visual))

    proc_summary = " | ".join([f"{p}:{len(process_cores.get(p, []))}" for p in PROCESSES])
    logging.info(f"Process cores -> {proc_summary}")

# =============================
# DASHBOARD COMMUNICATION
# =============================
def update_dashboard(cpu_usage, cpu_count):
    allocations = {
        p: ", ".join([f"CPU{cid}" for cid in process_cores.get(p, [])])
        for p in PROCESSES
    }
    payload = {
        "cpu_usage": round(cpu_usage, 1),
        "cpu_count": cpu_count,
        "allocations": allocations
    }

    try:
        requests.post(DASHBOARD_URL, json=payload, timeout=2)
    except requests.exceptions.RequestException as e:
        logging.warning(f"Dashboard update failed: {e}")

# =============================
# MAIN LOGIC
# =============================
def get_vm_cpu_usage():
    """Fetch CPU usage from VM agent."""
    try:
        res = requests.get(VM_AGENT_URL, timeout=2)
        if res.status_code == 200:
            return res.json().get("cpu", 0.0)
    except Exception as e:
        logging.warning(f"VM agent error: {e}")
    return random.uniform(5, 40)  # fallback

def hotplug_logic(cpu_usage):
    """Simulate dynamic scaling based on usage."""
    total_cores = len(core_allocation)
    free_cores = [cid for cid, owner in core_allocation.items() if owner is None]

    if cpu_usage > CPU_THRESHOLD_HIGH and free_cores:
        cid = free_cores.pop()
        target_proc = random.choice(PROCESSES)
        reallocate_core(cid, target_proc)
        log_allocation()
        return

    if cpu_usage < CPU_THRESHOLD_LOW:
        for cid, owner in list(core_allocation.items()):
            if owner is not None and random.random() < 0.3:
                reallocate_core(cid, None)
        log_allocation()

def main():
    logging.info("Starting Core-Level Dynamic CPU Controller...")

    cpu_count = 4
    for i in range(cpu_count):
        proc = random.choice(PROCESSES)
        reallocate_core(i, proc)

    log_allocation()

    while True:
        usage = get_vm_cpu_usage()
        active_count = sum(1 for o in core_allocation.values() if o not in (None, "OFF"))
        logging.info(f"Total Usage: {usage:.1f}% | Cores Active: {active_count}")
        log_allocation()

        hotplug_logic(usage)
        update_dashboard(usage, cpu_count)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

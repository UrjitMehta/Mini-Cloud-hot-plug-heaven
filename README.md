# Hot-Plug Heaven: Dynamic AI Workloads in a Mini IaaS Cloud

Hot-Plug Heaven is a centralized, conservative, utilization-aware core allocation controller designed for distributed compute environments. It manages multiple agents (worker VMs or nodes), provides global core abstraction, performs intelligent scheduling, and exposes a live dashboard for monitoring system state in real time. The system includes a threaded Flask control plane, a persistent logging layer, and a background scheduler implementing dynamic core allocation and safe, conservative core stealing.

---

##  Features

- **Threaded Flask API** for low-latency `/request`, `/complete`, and `/register` operations  
- **Background Scheduler** handling allocation decisions independently of API latency  
- **Global Core Map** unifying distributed agent cores into a single indexed space  
- **Conservative Core Stealing** based on real CPU usage with minimum-core safety enforcement  
- **SQLite Persistent Logging** for auditing allocations, steals, completions, and registrations  
- **Real-Time Dashboard** (HTML/JS) showing:  
  - Global core grid with color-coded ownership  
  - Pending FIFO queue  
  - All live allocations  
  - Live per-agent job telemetry (cores, CPU%, PIDs)  
  - Rolling activity log (latest events first)

---

##  Architecture Overview

Each agent registers with the controller, advertising its endpoint URL, total cores, and global-index offset. The controller builds a unified global core map (`CORE_MAP`) and uses a central scheduler to assign cores to jobs. If an agent lacks sufficient free cores, the scheduler can *selectively steal* underutilized cores from other jobs across the cluster, guided by a CPU-percent-based estimator while respecting `MIN_CORES_PER_JOB`.

A full suite of runtime structures (`AGENTS`, `CORE_MAP`, `ALLOCATIONS`, `JOB_REQUEST`, `PENDING`) tracks the complete system state. All state transitions are protected by a global lock, guaranteeing internal consistency under concurrent operations. The system achieves a balance between responsiveness (threaded Flask) and deterministic scheduling cycles (background loop).

---

##  Endpoints

### `POST /register`
Registers an agent.  
Payload: `{ vm_name, endpoint, total_cores, core_offset }`

### `POST /request`
Job requests core allocation.  
Payload: `{ vm, job, pid, cores_requested }`

### `POST /complete`
Job notifies completion and frees its cores.  
Payload: `{ vm, job }`

### `GET /summary`
Provides full system state for the dashboard.

### `/`
Serves the real-time dashboard UI.

---

##  Running the Controller

```bash
python3 controller.py 
```

The controller auto-detects host IP and exposes the dashboard on:
```bash
http://<controller-ip>:5000 
```
The scheduler thread starts automatically.

##  Logging
All significant events are appended to:
```bash
alloc_log.db
```
under the log table (ts, action, detail).
The UI also maintains an in-memory rolling activity buffer.

## Dashboard Preview

- Core Grid: Shows each core as free or owned by a job (agentA, agentB, …)

- Pending Queue: Visible FIFO list of queued jobs

- Allocations View: Global record of assigned cores

- Live Jobs: Queries each agent's /status endpoint for real-time CPU and core usage

- Activity Log: Last ~200 state transitions

## Scheduler Logic

- Direct Fit

  - Checks agent-local free cores; if enough exist, allocates immediately.

- Utilization-Aware Stealing

  - Queries every agent’s job CPU% via /status
  
  - Estimates effective usage and identifies spare cores
  
  - Ensures jobs never drop below MIN_CORES_PER_JOB
  
  - Frees stolen cores and reallocates them to the requesting job

- Atomic State Updates

  - All modifications to global state mappings occur under strict locking.

## Directory Structure

project/
│
├── controller.py(windows side)
├── agent_instance.py
├── worker.py
├── agents.json
├── README.md
└── alloc_log.db  (auto-created)

## Notes

- Agents must expose /allocate, /release, and /status endpoints.

- Controller handles failure tolerantly: unreachable agents do not break scheduling.

- Ideal for research, distributed orchestration demos, and dynamic compute experiments.

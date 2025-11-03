# Windows Host Overview

This folder contains all components that run on the Windows host system — responsible for monitoring VM CPU usage, dynamically hot-plugging CPU cores, and displaying a live dashboard.

## Components

### 1️⃣ Controller
- **File:** `controller/dynamic_cpu_controller.py`
- **Purpose:** Connects to the VM's monitoring agent, decides how many cores to plug/unplug using VBoxManage commands.
- **Utilities:** `controller_utils.py` provides logging, core reassignment logic, and payload handling.

**Run:**
```bash
cd host/controller
python dynamic_cpu_controller.py

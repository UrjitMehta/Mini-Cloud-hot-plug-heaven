# Hot-Plug Heaven — Mini IaaS CPU Hot-Plug Prototype

**Short:** a small-scale IaaS prototype that dynamically hot-plugs/unplugs CPU cores from VMs based on real-time usage (VM agent reports) to improve utilization in shared HPC-like environments.

---

## Repo layout
See `/host` for Windows host-side code (controller + dashboard + simulator) and `/vm` for VM-side agent files. Documents and diagrams are in `/docs`.

---

## Quickstart

### Prerequisites
- Windows host:
  - Python 3.10+ installed
  - VirtualBox (7.x)
  - Git, VS Code (with "Remote - SSH" optional)
- Ubuntu VM:
  - Python 3.10+
  - VirtualBox Guest Additions (for better integration)
  - Network access between host and VM (host-only or bridged)

---

## Setup — Windows host (controller & dashboard)

1. Clone repo:
   ```bash
   git clone https://github.com/<your-org>/hot-plug-heaven.git
   cd hot-plug-heaven/host/controller

# Hive: Usage and Testing Guide

## 1. Environment Setup

### 1.1 Prerequisites (Both Machines)
* **OS:** Windows 10 (1903+) or Windows 11.
* **Hardware:** WiFi adapter with WiFi Direct (P2P) support. 
  * *Check:* `netsh wlan show drivers` (Look for "Hosted network supported: Yes").
* **Firewall:** Run `.\setup-hive.ps1` as Administrator (or `./setup-hive.sh` on Linux) once to secure the 5000-5011 port range for Hive binaries.

### 1.2 Deployment Modes
* **Source Mode:** Run `python -m app.main` from the repo root (Python 3.11+ required).
* **Bundle Mode:** Run `.\Hive.exe` from the `dist/Hive` folder (No Python/MSVC required).

---

## 2. CLI and Launch Options

The Hive executable supports the following orchestration flags:

* `--debug`: Enables verbose log output for both Python and the C++ Agent.
* `--inspector`: Performs an end-to-end diagnostic check of local WiFi hardware.
* `--pin <4-digit PIN>`: Sets the Room PIN for session encryption (Default: 0000).
* `--mock <path>`: Allows developers to point to a custom mock agent binary.

---

## 3. Swarm Workflow (Real Hardware)

### Phase 1: Swarm Formation
1. **Host Swarm:** Launch Node A and click "Host Swarm." 
   * *Log Signature:* `[Network] Started on 192.168.137.1 (control:5000)`.
2. **Join Swarm:** Launch Node B and click "Join Swarm." 
   * *Log Signature:* `[Agent] ← {'assigned_ip': '192.168.137.x', ...}`.
3. **Verification:** Both nodes should agree on a **LEADER** (Amber badge) based on hardware Vitality Scores.

### Phase 2: High-Speed Transfer
1. Initiate a transfer from the **Transfer** tab.
2. **Handshake:** The sender waits for the receiver to signal `MSG_P2P_DONE`.
3. **Verification:** The sender log must display `(Confirmed by Peer)` to ensure a clean 100% completion with no buffer loss.

---

## 4. Automated Testing (For Developers)

Hive includes simulations that do not require real WiFi hardware.

### 4.1 Local Swarm Simulation
Spawns three nodes on one machine using localhost port offsets.
```powershell
pytest tests/integration/test_local_cluster.py -v -s
```

### 4.2 Integration Suite
Runs exhaustive protocol and resume-flow logic.
```powershell
$env:RUN_INTEGRATION="1"
python dist_tools\build.py
```

### 4.3 Hardware Integration (Single Machine)
Requires a WiFi adapter; creates real `DIRECT-` interfaces.
```powershell
$env:RUN_HW_TEST="1"
pytest tests/integration/test_hybrid_data_plane.py -v -s
```

---

## 5. Troubleshooting

* **Issue: "Requesting Permission" hangs.**
    * *Fix:* Ensure `setup-hive.ps1` was run on both machines.
* **Issue: "Network name no longer available" (WinError 64).**
    * *Fix:* A transient link drop. Hive v1.1.1 handles this by re-polling the adapter automatically.
* **Issue: Node visibility is slow.**
    * *Fix:* Close 3rd party P2P apps (e.g. KDE Connect) that might be competing for the radio.

# Hive: Verification & Validation Results (v1.1.0)

**1. FAULT TOLERANCE & AUTO-RECOVERY**
* **Test:** Wi-Fi disable/enable simulation during active transfer.
* **Result:** PASS
* **Mechanism:**
    * C++ background thread detects OS P2P virtual adapter teardown immediately (< 2s).
    * **Hardening:** Added a background `_ip_poll_task` in Python to handle the delay between the link coming up and Windows assigning an IP. This prevents the "0.0.0.0" broadcast bug found in early builds.
    * **Resilience:** Receiver handles "Network name no longer available" (WinError 64) via try-except cleanup, allowing the swarm to re-form and the transfer to resume automatically.

**2. CHUNK SIZE OPTIMIZATION (WINDOWS ASYNCIO)**
* **Test:** Throughput vs. Event Loop Latency.
* **Result:** **128KB (131,072 bytes)** validated as the architectural optimum for Windows `asyncio`.
* **The Truth:** 
    * Earlier builds targeted 1MB, but real-world testing proved that 1MB chunks block the Python event loop for too long (>150ms). 
    * This caused UI lag and heartbeat timeouts. Shifting to 128KB allows for a high frequency of `await drain()` calls, keeping the pipe full while ensuring the swarm leader never misses a heartbeat beacon.
    * C++ relay buffers were matched to 128KB to eliminate context-switch bottlenecks.

**3. MULTI-INSTANCE CLUSTER SIMULATION**
* **Test:** Spawning a 3-node swarm on a single machine using localhost.
* **Result:** PASS
* **Mechanism:** 
    * Successfully verified **Dynamic Port Decoupling**. Node B and C correctly auto-incremented to ports 5002 and 5004.
    * **Native Discovery:** Nodes found each other automatically over loopback using **Multi-Port UDP Broadcast** (shouting on ports 5000-5010).

**4. DATA INTEGRITY & EOT SYNCHRONIZATION**
* **Test:** Large file transfer (100MB+) over high-latency links.
* **Result:** PASS (Resolved the 96% Hang)
* **Mechanism:**
    * **Handshake:** Implemented `MSG_P2P_DONE`. The sender now stays connected until the receiver confirms the file is successfully synced to disk (`os.fsync`). This prevents the physics bug where radio buffers were discarded during premature shutdown.
    * **Integrity:** SWARM protocol utilizes AES-256-GCM. If any bit-flips occur during airtime, the GCM tag verification fails and the chunk is rejected.

**5. OPERATIONAL RANGE & PENETRATION**
* **Test:** Line-of-Sight (LoS) vs. Obstructed environment connectivity.
* **Mechanism:** Tested via 802.11ac hardware. 2.4 GHz performs significantly better through concrete, while 5 GHz maximizes throughput in open space.

| Frequency Band | Environment | Effective Range |
| :--- | :--- | :--- |
| **2.4 GHz** | Indoor (Obstructed) | 30 – 50 meters |
| **2.4 GHz** | Outdoor (LoS) | 100 – 200 meters |
| **5 GHz** | Indoor (Obstructed) | 15 – 30 meters |
| **5 GHz** | Outdoor (LoS) | 60 – 90 meters |

**6. IOT POWER USAGE & ELECTION STABILITY**
* **Test:** Battery preservation during leader election.
* **Result:** PASS
* **Mechanism:** Vitality Score algorithm prioritizes AC power.
* **Adaptive Discovery:** Once a swarm is formed, discovery frequency drops from every 2s to **every 10s**. This reduces radio airtime usage by 80%, preserving battery on mobile nodes and reducing "sawtooth" noise during active file transfers.

**7. ONE-TO-ONE CONNECTION SECURITY**
* **Test:** Resistance to brute-force and payload interception.
* **Result:** PASS
* **Mechanism:**
    * **Key Derivation:** Argon2id (ASIC-resistant).
    * **Identity Challenge:** During `P2P_HANDSHAKE`, the Sender challenges the Receiver to sign a random nonce using the PIN key. This prevents rogue nodes from hijacking a transfer even if they spoof a peer's UUID.
    * **Firewall:** Port-restricted app-bound rules block 3rd-party apps (e.g. KDE Connect) from accessing Hive's dynamic port range.

**8. QUALITY OF SERVICE (QoS)**
* **Test:** Throughput saturation and network latency.
* **Mechanism:** Wi-Fi Direct airtime efficiency (single-hop).

| Metric | 802.11n (2.4 GHz) | 802.11ac (5 GHz) |
| :--- | :--- | :--- |
| **Throughput** | 20 – 50 Mbps | 150 – 400 Mbps |
| **Latency (Ideal)** | 2 – 5ms RTT | 2 – 5ms RTT |
| **Latency (Congested)**| 15 – 30ms RTT | 10 – 25ms RTT |

# Hive: Internal Logic & Architectural Details

## 1. Async Hardware Agent Bridge (`app/core/agent.py`)

The `AsyncHardwareAgent` class serves as a high-speed bridge between the Python controller and the OS-specific C++ hardware agents.

### Boot Sequence
On startup, the agent binary immediately emits a `READY` status message:
```json
{"type":"STATUS", "state":"READY", "message":"Hardware agent initialized", "version": "1.1.1"}
```
The Python `start()` method is a blocking coroutine that waits for this specific signal. This ensures that no commands (like `SCAN` or `CREATE_GROUP`) are sent before the low-level Wi-Fi stack is fully initialized.

### Async Communication Pattern
*   **Stdout Reader:** A dedicated background task reads newline-delimited JSON from the agent's stdout and pushes decoded dictionaries into an `asyncio.Queue`.
*   **Stderr Forwarder:** A separate task monitors the agent's stderr. Low-level C++ logs are captured here and injected into the Python logging system.
*   **Command Dispatch:** Commands are serialized to JSON and followed by a newline. Protocol requires immediate flushing of the stdin pipe to ensure low latency.

---

## 2. Application Controller (`app/core/controller.py`)

The `AppController` acts as the central orchestrator, bridging the `customtkinter` UI thread and the `asyncio` networking thread.

### Event Dispatching
Since the UI runs in the main thread (blocking) and the hardware agent/network logic runs in an async loop, the controller uses a thread-safe dispatcher. The `_ui_call` method schedules UI updates to run on the next tick of the Tkinter mainloop, preventing race conditions and GUI freezes.

### Node Identity
*   **UUID:** Derived from the system's MAC address (via `uuid.getnode()`) to ensure consistent identity across sessions.
*   **Vitality Score:** Calculated by the C++ agent based on AC power status, RAM, and CPU cores. This score is shared across the network and determines the "Healthiest" node to be elected as the **Swarm Leader**.

---

## 3. P2P Networking (`app/core/network.py`)

Hive uses a custom protocol for infrastructure-free discovery and session management.

### Discovery & Heartbeats
The `NetworkManager` runs a UDP broadcast loop (Port 5000). Every 2 seconds, it sends an encrypted "Discovery" packet containing its UUID, Name, and Vitality Score. This allows nodes to find each other without a central router or access point.

### Leader Election Logic
Election is autonomous and decentralized. Every node maintains a list of peers. The node with the **highest Vitality Score** (using UUID as a tie-breaker) is locally marked as the `host_uuid`. This ensures the node with the best battery/CPU handles the routing and session management. Hive distinguishes between the physical Group Owner and the logical Swarm Leader.

---

## 4. Security Manager (`app/core/security.py`)

### Cryptographic Stack
*   **KDF (Argon2id):** The Room PIN is converted into a 256-bit key using Argon2id with a fixed salt. This is performed once at startup.
*   **Encryption (AES-256-GCM):** Every packet sent over the air is encrypted using AES-GCM. 
*   **Nonce Handling:** A random 12-byte nonce is generated for every single packet and prepended to the ciphertext. This prevents replay attacks and ensures that identical heartbeats produce different encrypted outputs.

---

## 5. Data Plane (`app/core/data_plane.py`)

### Resumable Transfers
Before starting a file receive, the Data Plane checks the existing file size on disk.
1.  If a partial file exists, its size is sent back in the `P2P_ACK` message as a `resume_offset`.
2.  The sender then seeks to that offset before streaming bytes.
3.  This allows Hive to recover from physical link drops (common in Wi-Fi Direct) without restarting large file transfers from 0%.

### Optimized Chunk Size
File data is encrypted and streamed in **128 KB (131,072 byte)** chunks. 
*   **Performance:** 128KB was empirically validated as the "sweet spot" for Windows `asyncio`. 
*   **Latency:** It minimizes event-loop blocking (found with 1MB chunks) while maintaining high throughput by saturating the C++ raw relay pipeline.
*   **Consistency:** Both Windows and Linux agents use matching 128KB relay buffers to ensure high-speed cross-platform transfers.

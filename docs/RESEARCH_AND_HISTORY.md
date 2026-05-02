# Hive: Research Journey and Project Rationale

## 1. Project Evolution

### 1.1 Original Concept
The project was conceived as a monolithic Python application. Research during Phase 1 revealed that Python lacked the native low-level hooks required to manage WiFi Direct drivers reliably across Windows and Linux. The architecture was subsequently pivoted to the current Sidecar Pattern (C++ Hardware Agents + Python Logic).

### 1.2 Connectivity Breakthroughs
* Windows: Discovery originally utilized the WiFiDirectDevice API, which proved unreliable due to NCSI (Network Connectivity Status Indicator) interference. The implementation was shifted to utilize the WiFiAdapter SSID scanning method to discover DIRECT- networks, which bypasses internet-connectivity checks.
* Linux: Implementation shifted from raw wpa_cli scripting to a D-Bus based signal architecture, enabling asynchronous confirmation of group creation and peer discovery.

## 2. Decision Log

### 2.1 Incumbency Rule
The system prioritizes network stability over peak performance. Preemption (replacing an active Session Host with a higher-scoring newcomer) is explicitly forbidden to prevent unnecessary radio link renegotiation and state migration complexity.

### 2.2 Standardized SSID Prefix
SSID prefixes were standardized from DIRECT-HIVE- to DIRECT-HV- to reduce advertisement overhead and provide a more professional network appearance. All agents utilize the professional HVAGENT UUID for service distinction.

### 2.3 Async vs. Synchronous Blocking
Early prototypes utilized sleep() calls to wait for hardware initialization. Current production code utilizes event-driven callbacks (Windows StatusChanged) and D-Bus filters (Linux) with 10-second condition variable timeouts to ensure deterministic state transitions.

## 3. Unique Value Proposition

### 3.1 Ruthless Mode (2.4 GHz)
Hive is designed for survival and emergency scenarios. While 5 GHz offers higher speeds, Hive implements a Ruthless Mode to force 2.4 GHz operation, ensuring compatibility with legacy hardware, IoT sensors, and long-range drone links.

### 3.2 True Infrastructure Independence
Unlike contemporary solutions that rely on mDNS or existing LAN infrastructure, Hive manages the physical radio layer. It is capable of bootstrapping a network in environments where no other wireless signals exist.

### 3.3 Bootstrap Platform Vision
File transfer is implemented as the foundational layer. The long-term vision for Hive is a deployment platform for infrastructure-less applications, including emergency chat, mesh-based sensor telemetry, and offline firmware distribution.

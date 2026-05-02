# Hive: Technical Specification and Protocol

## 1. Governance and Election Logic

### 1.1 Vitality Score Calculation
The system calculates a fitness score for each node to determine suitability for the **Swarm Leader** role.

$$Score = 50 + \underbrace{\begin{cases} +50 & \text{AC Power} \\ -20 & \text{Battery} \end{cases}}_{\text{Power Source}} + \underbrace{15 \cdot \mathbb{I}(R > 8) + 15 \cdot \mathbb{I}(R > 16)}_{\text{RAM (Cumulative)}} + \underbrace{20 \cdot \mathbb{I}(C > 6 \text{ Cores})}_{\text{Logical Cores}}$$

Tie-breaking is performed lexicographically using the Node UUID.

### 1.2 Non-Preemption Governance
Stability is prioritized over performance. If a Swarm Leader is currently active, election bids are ignored. A change in the Leader role occurs only upon the failure (heartbeat timeout) or voluntary departure of the current leader.

### 1.3 Role Separation
Hive distinguishes between the **Physical Network Role** and the **Logical Swarm Role**:
* **Interface Role:** Determines WiFi hierarchy (Group Owner vs. Peer Node).
* **Swarm Status:** Determines Hive hierarchy (Leader vs. Peer).

## 2. Protocol Specification (SWARM)

### 2.1 The Binary Header (12 Bytes)
All network traffic (UDP/TCP) starts with a 12-byte "BZZZ" header to filter junk traffic and ensure protocol alignment.

| Offset | Field | Type | Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | **Magic** | `uint32` | `0x425A5A5A` | ASCII "BZZZ". |
| `0x04` | **Version** | `uint8` | `0x01` | Protocol Version. |
| `0x05` | **Type** | `uint8` | `Enum` | Message Type ID (see 2.2). |
| `0x06` | **Flags** | `uint16` | `0x0000` | Reserved. |
| `0x08` | **Length** | `uint32` | `Int` | Length of the encrypted payload. |

### 2.2 Message Types
| ID | Constant | Description |
| :--- | :--- | :--- |
| `0x01` | `MSG_DISCOVERY` | UDP Broadcast beacon (UUID, Score). |
| `0x02` | `MSG_HOST_WELCOME` | Peer registry sync from Leader to new node. |
| `0x03` | `MSG_HEARTBEAT` | Keep-alive from Peer to Leader. |
| `0x10` | `MSG_P2P_REQ` | Permission request to send a file. |
| `0x11` | `MSG_P2P_PERMIT` | Authorization response with target port. |
| `0x20` | `MSG_P2P_HANDSHAKE` | Sender-to-Receiver identity validation. |
| `0x21` | `MSG_P2P_ACK` | Handshake acceptance and resume offset. |
| `0x30` | `MSG_P2P_DATA` | (Reserved) For future framed data streaming. |
| `0x31` | `MSG_P2P_DONE` | **EOT Handshake:** Receiver confirmation. |
| `0x40` | `MSG_SH_RETIRE` | Voluntary departure notification from Leader. |

### 2.3 Dynamic Transport Ports
Hive supports multiple instances per machine using dynamic port offsets:
* **Base Port 5000 (UDP):** Decentralized Discovery and Vitality Beacons.
* **Base Port 5000 (TCP):** Session Management, Election, and Handshakes.
* **Base Port 5001 (TCP):** Hybrid Data Plane (Raw streaming).
* **Range:** 5000 - 5010 for control/discovery and 5001 - 5011 for data (auto-incremented if ports are busy).

## 3. Data Plane Implementation

Hive utilizes a **Hybrid Bridge** architecture to combine Python's ease of security management with C++'s hardware resilience.

### 3.1 The Hybrid Bridge
1. **Python Side:** Encrypts file chunks (128KB) using AES-256-GCM and writes them to a local loopback TCP socket.
2. **C++ Agent Side:** Reads from the local loopback and forwards the raw bytes directly to the peer's network socket.
3. **Optimized Buffering:** Both layers utilize **128KB buffers** to maximize throughput on WiFi Direct links while preventing `asyncio` event-loop blocking on Windows.

### 3.2 Endpoints (Multi-Instance)
* **Windows:** Local TCP Bridge (Dynamic loopback port).
* **Linux:** Unix Domain Socket (`/tmp/hive_<port>.sock`).

## 4. Security Model

### 4.1 Encryption
* **Algorithm:** AES-256 (GCM Mode) for Authenticated Encryption.
* **Key Derivation:** Argon2id (Iterations: 2, Memory: 64MB).
* **Scope:** All network packets (Control and Data) are encrypted.

### 4.2 Firewall Security (App-Bound)
Windows Firewall rules are restricted to the specific Hive executables (`Hive.exe` and `HiveAgent.exe`) and limited to the `5000-5011` port range to minimize attack surface.

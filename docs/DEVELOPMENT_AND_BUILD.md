# Hive: Development, Build, and Integration

## 1. Build Environment

### 1.1 Windows Compilation
* Toolchain: MSVC 2022 (cl.exe).
* Requirements: Windows 10 SDK (10.0.19041.0+), C++/WinRT.
* Procedure:
  1. Navigate to agents/win32.
  2. Execute build.bat.
  3. Binary produced: HiveAgent.exe.

### 1.2 Linux Compilation
* Toolchain: g++ (GCC).
* Requirements: libdbus-1-dev, build-essential.
* Procedure:
  1. Navigate to agents/linux.
  2. Execute build.sh.
  3. Binary produced: HiveAgent.

## 2. Python Integration (Component B)

The Python application communicates with the C++ agents via standard streams for control and local sockets for data.

### 2.1 Control Plane
Implementation utilizes the `subprocess` module with text mode and line buffering. Every command sent must be followed by a flush operation to maintain the agent's internal state machine synchronization.

### 2.2 Data Plane Optimization
1. **Hybrid Bridge:** C++ Agent starts a TCP bridge on a local dynamic port.
2. **Buffer Symmetry:** Both Python and C++ layers utilize **128KB (131,072 bytes)** buffers.
3. **EOT Handshake:** The system implements a mandatory **End-of-Transfer Handshake** (`MSG_P2P_DONE`). The Sender awaits confirmation from the Receiver before terminating the data plane to ensure no radio-buffer loss.
4. **Port Decoupling:** Hive utilizes dynamic port offsets (5000-5010 for control/discovery and 5001-5011 for data), enabling multiple instances to run on a single machine for cluster simulation.

## 3. Verified Implementations

### 3.1 Linux Native D-Bus
The Linux agent utilizes pure native D-Bus calls for all connection state changes, providing event-driven asynchronous confirmation of group events without the overhead of external CLI wrappers.

### 3.2 Swarm Election
Leaders are elected based on hardware **Vitality Scores**. If a node has AC Power, high RAM, and multiple cores, it is promoted to **Swarm Leader** to coordinate the peer registry and authorize file transfers.

### 3.3 Security
Port-restricted **App-Bound Firewall Rules** ensure that only the verified Hive binaries can communicate over the specified port range.

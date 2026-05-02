import asyncio
import json
import os
import pytest
import socket
import struct
import subprocess
import sys
import threading
import time
from app.core.security import SecurityManager
from app.core.data_plane import DataPlane

def log_reader(name, stream):
    for line in iter(stream.readline, ''):
        print(f"[{name}] {line.strip()}")

# This test requires the HiveAgent binary to be built in agents/win32 or agents/linux
@pytest.mark.skipif(os.environ.get("RUN_HW_TEST") != "1", reason="Requires actual built agents and hardware")
def test_end_to_end_file_transfer():
    async def run_test():
        # Setup paths
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        agent_bin = os.path.join(base_dir, "agents", "win32", "HiveAgent.exe") if sys.platform == "win32" else \
                    os.path.join(base_dir, "agents", "linux", "HiveAgent")
        
        if not os.path.exists(agent_bin):
            pytest.fail(f"Agent binary not found at {agent_bin}. Build it first.")

        room_pin = "12345678"
        sec = SecurityManager(room_pin)
        
        async def read_resp(proc, name):
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, proc.stdout.readline)
                if not line: return None
                if line.strip().startswith("{"):
                    return json.loads(line)

        # 1. Start Agents
        proc_recv = subprocess.Popen([agent_bin, "--debug"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        proc_send = subprocess.Popen([agent_bin, "--debug"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        threading.Thread(target=log_reader, args=("RECV STDERR", proc_recv.stderr), daemon=True).start()
        threading.Thread(target=log_reader, args=("SEND STDERR", proc_send.stderr), daemon=True).start()

        print("Waiting for agents READY...")
        while True:
            r = await read_resp(proc_recv, "RECV")
            if r and r.get("state") == "READY": break
        while True:
            r = await read_resp(proc_send, "SEND")
            if r and r.get("state") == "READY": break

        try:
            # 2. Setup Data Plane for Receiver (Server)
            print("Starting Receiver Data Plane...")
            proc_recv.stdin.write(json.dumps({"type": "START_DATA_PLANE", "peer_port": 6001}) + "\n")
            proc_recv.stdin.flush()
            resp_recv = await read_resp(proc_recv, "RECV")
            bridge_recv = resp_recv.get("bridge_port")
            print(f"Receiver Bridge Port: {bridge_recv}")
            
            # 3. Setup Data Plane for Sender (Client)
            print("Starting Sender Data Plane...")
            proc_send.stdin.write(json.dumps({"type": "START_DATA_PLANE", "peer_ip": "127.0.0.1", "peer_port": 6001}) + "\n")
            proc_send.stdin.flush()
            resp_send = await read_resp(proc_send, "SEND")
            bridge_send = resp_send.get("bridge_port")
            print(f"Sender Bridge Port: {bridge_send}")

            # 4. Connect Python DataPlane objects
            dp_send = DataPlane(sec)
            dp_recv = DataPlane(sec)
            
            test_file = os.path.join(base_dir, "test_data.bin")
            out_file = os.path.join(base_dir, "received_data.bin")
            data = os.urandom(1024 * 1024) 
            with open(test_file, "wb") as f: f.write(data)

            async def receiver_flow():
                print(f"Receiver: Connecting to bridge port {bridge_recv}...")
                await dp_recv.connect(str(bridge_recv))
                print("Receiver: Receiving...")
                await dp_recv.receive_file(out_file, len(data))
                print("Receiver: Done.")

            async def sender_flow():
                print(f"Sender: Connecting to bridge port {bridge_send}...")
                await dp_send.connect(str(bridge_send))
                print("Sender: Sending...")
                await dp_send.send_file(test_file)
                print("Sender: Waiting for agent to drain...")
                await asyncio.sleep(1.0)
                print("Sender: Done.")

            print("Starting concurrent flows...")
            await asyncio.gather(receiver_flow(), sender_flow())

            # 6. Verify
            with open(out_file, "rb") as f:
                received = f.read()
                assert len(received) == len(data)
                assert received == data
                print("✓ SUCCESS: File transferred and verified via TCP Bridge!")

        finally:
            proc_recv.terminate()
            proc_send.terminate()
            if 'test_file' in locals() and os.path.exists(test_file): os.remove(test_file)
            if 'out_file' in locals() and os.path.exists(out_file): os.remove(out_file)

    asyncio.run(run_test())

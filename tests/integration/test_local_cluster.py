import asyncio
import json
import pytest
import os
import shutil
import uuid as _uuid_mod
from typing import List, Optional

from app.core.controller import AppController
from tests.conftest_utils import SecurityManagerMock

class MockAsyncHardwareAgent:
    """
    A mock agent that simulates hardware events without a real subprocess.
    """
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.response_queue = asyncio.Queue()
        self.running = False
        self.version = "1.1.1"
        self.vitality_score = 50
        self._exe_path = "mock_agent.exe"

    async def start(self):
        self.running = True
        # Immediate READY signal
        await self.response_queue.put({
            "type": "STATUS", 
            "state": "READY", 
            "version": self.version,
            "message": "Mock Agent Ready"
        })

    async def stop(self):
        self.running = False

    async def send_command(self, cmd):
        t = cmd.get("type")
        if t == "CREATE_GROUP":
            await self.response_queue.put({
                "type": "GROUP_CREATED",
                "status": "active",
                "group_name": f"DIRECT-HV-{self.node_id}",
                "is_group_owner": True,
                "passphrase": "password"
            })
        elif t == "CONNECT":
            await self.response_queue.put({
                "type": "CONNECTED",
                "assigned_ip": "127.0.0.1",
                "remote_ip": "127.0.0.1",
                "group_uuid": cmd.get("uuid")
            })
        elif t == "GET_TELEMETRY":
            await self.response_queue.put({
                "type": "TELEMETRY",
                "vitality_score": self.vitality_score
            })
        elif t == "START_DATA_PLANE":
            await self.response_queue.put({
                "type": "DATA_PLANE_STARTED",
                "bridge_port": 0,
                "role": "server" if not cmd.get("peer_ip") else "client"
            })
        elif t == "STOP_DATA_PLANE":
             await self.response_queue.put({"type": "DATA_PLANE_STOPPED"})

def test_multi_instance_election_and_failover(tmp_path, monkeypatch):
    """
    Simulates a 3-node cluster on localhost.
    Tests:
    1. Simultaneous startup and port decoupling.
    2. Discovery and Peer Registration (NATIVE UDP DISCOVERY).
    3. Host Election based on Vitality Scores.
    4. Failover when the Host goes offline.
    """
    async def run_test():
        nodes = []
        
        # 1. Setup Phase
        async def create_node(name, score):
            node_dir = tmp_path / name
            node_dir.mkdir()
            
            # Isolation: Patch _runtime_base_dir for this specific instantiation
            import app.core.controller as ctrl_mod
            def get_dir(d=str(node_dir)): return d
            monkeypatch.setattr(ctrl_mod, "_runtime_base_dir", get_dir)
            
            c = AppController(room_pin="1234", agent_override=None, debug=True)
            c.my_name = name
            c.my_uuid = str(_uuid_mod.uuid4())
            c.agent = MockAsyncHardwareAgent(name)
            c.agent.vitality_score = score
            
            # Avoid real DataPlane connections
            async def fake_dp_connect(*args): pass
            c._on_data_plane_started = fake_dp_connect
            
            return c

        node_a = await create_node("NODE_A", 30)
        node_b = await create_node("NODE_B", 90)
        node_c = await create_node("NODE_C", 50)
        
        all_nodes = [node_a, node_b, node_c]
        
        try:
            # 2. Startup Phase (Concurrent)
            for n in all_nodes:
                n.start()
            
            # Wait for agents to be ready and NetworkManagers to be created
            for n in all_nodes:
                for _ in range(50):
                    if n.network is not None: break
                    await asyncio.sleep(0.1)
                assert n.network is not None, f"NetworkManager not created for {n.my_name}"

            # Trigger Group Creation and Connection via official API
            node_a.host_group()
            await asyncio.sleep(0.5)
            node_b.join_group("DIRECT-HV-NODE_A")
            await asyncio.sleep(0.5)
            node_c.join_group("DIRECT-HV-NODE_A")
            
            # Wait for native UDP discovery to link the swarm
            # With multi-port broadcast, this should work automatically over 127.0.0.1
            await asyncio.sleep(5.0) 
            
            # Verify they got unique control ports
            ports = [n.network.control_port for n in all_nodes]
            print(f"Final detected ports: {ports}")
            assert len(set(ports)) == 3, f"Ports should be unique: {ports}"
            
            # 3. Swarm Verification
            node_b_uuid = node_b.my_uuid
            for n in all_nodes:
                # Every node should have discovered the other 2
                assert len(n.network.peers) == 2, f"{n.my_name} only found {len(n.network.peers)} peers"
                # Everyone should see NODE_B (score 90) as Leader
                assert n.network.host_uuid == node_b_uuid, f"{n.my_name} elected wrong leader"

            # 4. Failover Phase: Kill the Leader (NODE_B)
            node_b.shutdown()
            
            # Signal host lost and prune to survivors
            def kill_peer(survivor, dead_uuid):
                survivor.network.peers.pop(dead_uuid, None)
                if survivor.network.on_host_lost:
                    survivor.network.on_host_lost(dead_uuid)
                
            node_a._loop.call_soon_threadsafe(kill_peer, node_a, node_b_uuid)
            node_c._loop.call_soon_threadsafe(kill_peer, node_c, node_b_uuid)
            
            await asyncio.sleep(1.0)
            
            # Assert NODE_C (score 50) is now the leader for survivors
            node_c_uuid = node_c.my_uuid
            assert node_a.network.host_uuid == node_c_uuid
            assert node_c.network.host_uuid == node_c_uuid

        finally:
            for n in all_nodes:
                n.shutdown()

    asyncio.run(run_test())

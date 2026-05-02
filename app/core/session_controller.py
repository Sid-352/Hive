import asyncio
import logging
import socket

import psutil

from app.core.events import HiveEvent
from app.core.network import P2P_PORT

logger = logging.getLogger("hive.session")


class SessionController:
    def __init__(self, owner) -> None:
        self._owner = owner

    def scan_groups(self, duration: int = 10) -> None:
        owner = self._owner
        owner._submit(owner._send_agent_command({"type": "SCAN", "duration": duration}))
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "SCANNING")
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "SCANNING")

    def host_group(self, ruthless: bool = False) -> None:
        owner = self._owner
        owner._intended_state = "HOST"
        owner._connection_mode = "HOST"
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "ASSOCIATING")
        owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, "NONE")
        owner._submit(owner._send_agent_command({
            "type": "CREATE_GROUP",
            "device_id": owner.my_name[:8].upper(),
            "ruthless_mode": ruthless,
        }))
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "ASSOCIATING")

    def join_group(self, uuid: str) -> None:
        owner = self._owner
        owner._intended_state = "CLIENT"
        owner._connection_mode = "CLIENT"
        owner._target_uuid = uuid
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "ASSOCIATING")
        owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, "NONE")
        owner._submit(owner._send_agent_command({"type": "CONNECT", "uuid": uuid}))
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "ASSOCIATING")

    def leave_session(self) -> None:
        owner = self._owner
        owner._intended_state = "IDLE"
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "IDLE")
        owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, "NONE")
        owner._submit(owner._leave_session_async())

    async def on_connected(self, event: dict) -> None:
        owner = self._owner
        trace_id = event.get("trace_id", "AGENT-CONN")
        if owner._intended_state != "CLIENT":
            return
        if owner.network:
            owner.network.suppress_election_events = False
        owner._connection_mode = "CLIENT"
        logger.info("[Session][%s] Agent signaled connected", trace_id)

        local_ip = event.get("assigned_ip", "0.0.0.0")
        if local_ip == "0.0.0.0":
            for _ in range(5):
                for _, snics in psutil.net_if_addrs().items():
                    for snic in snics:
                        if snic.family == socket.AF_INET and snic.address.startswith("192.168.137."):
                            if snic.address != "192.168.137.1":
                                local_ip = snic.address
                                break
                if local_ip != "0.0.0.0":
                    break
                await asyncio.sleep(0.5)

        await owner._start_overlay(local_ip)
        await owner._send_agent_command({
            "type": "START_DATA_PLANE",
            "peer_port": owner.network.p2p_port if owner.network else P2P_PORT,
        })
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "CLIENT")
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "CONNECTED")
        owner.bus.publish(HiveEvent.SHOW_SCREEN, "session")

    async def on_group_created(self, event: dict) -> None:
        owner = self._owner
        trace_id = event.get("trace_id", "AGENT-HOST")
        if owner._intended_state != "HOST":
            return
        if owner.network:
            owner.network.suppress_election_events = False
        owner._connection_mode = "HOST"
        logger.info("[Session][%s] Agent signaled group created", trace_id)

        await owner._start_overlay("0.0.0.0")
        if owner._ip_poll_task and not owner._ip_poll_task.done():
            owner._ip_poll_task.cancel()
        owner._ip_poll_task = asyncio.create_task(owner._poll_for_valid_ip(event))

        await owner._send_agent_command({
            "type": "START_DATA_PLANE",
            "peer_port": owner.network.p2p_port if owner.network else P2P_PORT,
        })
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "HOST")
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "CONNECTED")
        owner.bus.publish(HiveEvent.SHOW_SCREEN, "session")

    async def poll_for_valid_ip(self, event: dict) -> None:
        owner = self._owner
        trace_id = event.get("trace_id", "IP-POLL")
        local_ip = event.get("assigned_ip", "0.0.0.0")
        if local_ip == "0.0.0.0":
            logger.info("[Session][%s] Polling for assigned P2P IP...", trace_id)
            for _ in range(10):
                for _, snics in psutil.net_if_addrs().items():
                    for snic in snics:
                        if snic.family == socket.AF_INET and snic.address.startswith("192.168.137."):
                            local_ip = snic.address
                            break
                if local_ip != "0.0.0.0":
                    break
                await asyncio.sleep(1.0)

        if local_ip != "0.0.0.0" and owner.network:
            logger.info("[Network] IP finalized: %s", local_ip)
            await owner.network.start(local_ip=local_ip)

    async def on_disconnected(self) -> None:
        owner = self._owner
        logger.info("[Session] Agent signaled disconnected")
        try:
            if owner.dp:
                await owner.dp.disconnect()
        except OSError:
            pass
        owner.dp = None

        await owner._send_agent_command({"type": "STOP_DATA_PLANE"})

        if owner.network:
            try:
                await owner.network.stop()
            except OSError:
                pass
            owner.network = None

        owner._connection_mode = "IDLE"
        owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "OFFLINE")
        owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, "NONE")
        owner.bus.publish(HiveEvent.SESSION_PEERS_UPDATED, [])
        owner.bus.publish(HiveEvent.TRANSFER_TARGETS_UPDATED, [])
        owner._leaving_session = False

        if owner._intended_state in ("HOST", "CLIENT"):
            logger.warning("[Session] Unexpected disconnection, initiating auto-recovery")
            if owner._recovery_task and not owner._recovery_task.done():
                owner._recovery_task.cancel()
            owner._recovery_task = asyncio.create_task(owner.recovery_controller.auto_recovery_loop())
        else:
            owner.bus.publish(HiveEvent.SHOW_SCREEN, "discovery")

    async def leave_session_async(self) -> None:
        owner = self._owner
        async with owner._leave_lock:
            if owner._leaving_session:
                return
            owner._leaving_session = True
        try:
            if owner._recovery_task and not owner._recovery_task.done():
                owner._recovery_task.cancel()
            if owner._ip_poll_task and not owner._ip_poll_task.done():
                owner._ip_poll_task.cancel()
            if owner.network and owner.network.host_uuid == owner.my_uuid:
                await owner.network.broadcast_retirement()
            cmd_type = "STOP_GROUP" if owner._connection_mode == "HOST" else "DISCONNECT"
            await owner._send_agent_command({"type": "STOP_DATA_PLANE"})
            await owner._send_agent_command({"type": cmd_type})
            if owner.network:
                await owner.network.stop()
            if owner.dp:
                await owner.dp.disconnect()
            owner.cancel_transfer()
            owner._pending_send = None
            owner._connection_mode = "IDLE"
            owner.network = None
            owner.dp = None
            owner.bus.publish(HiveEvent.NETWORK_STATE_CHANGED, "OFFLINE")
            owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, "NONE")
            owner.bus.publish(HiveEvent.SESSION_PEERS_UPDATED, [])
            owner.bus.publish(HiveEvent.STATUS_CHANGED, "OFFLINE")
            owner.bus.publish(HiveEvent.SHOW_SCREEN, "discovery")
        finally:
            owner._leaving_session = False

    async def start_overlay(self, ip: str) -> None:
        owner = self._owner
        if not owner.network:
            from app.core.network import NetworkManager
            owner.network = NetworkManager(
                owner.my_uuid,
                owner.my_name,
                0,
                owner._room_pin,
                owner.security,
                bus=owner.bus)
        await owner.network.start(local_ip=ip)
        owner.network._elect_host()

    def on_host_elected(self, uid: str) -> None:
        owner = self._owner
        if owner._connection_mode == "IDLE":
            return
        role = "HOST" if uid == owner.my_uuid else "CLIENT"
        owner.bus.publish(HiveEvent.SWARM_ROLE_CHANGED, role)
        owner._refresh_ui()

    def on_host_lost(self, uid: str) -> None:
        owner = self._owner
        if owner.network:
            owner.network.host_uuid = None
            owner.network._elect_host()

    def refresh_ui(self) -> None:
        owner = self._owner
        if not owner.network:
            return
        peers = [
            {
                "uuid": u,
                "name": i.get("name", u[:8]),
                "ip": i.get("ip", ""),
                "score": i.get("score", 0),
                "role": "HOST" if u == owner.network.host_uuid else "CONNECTED",
            }
            for u, i in owner.network.peers.items()
        ]
        owner.bus.publish(HiveEvent.SESSION_PEERS_UPDATED, peers)
        owner.bus.publish(HiveEvent.TRANSFER_TARGETS_UPDATED, peers)

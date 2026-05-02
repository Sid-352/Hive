import asyncio
import json
import logging
import socket
import struct
import time
import psutil
import ipaddress
import uuid
import statistics
from typing import Dict, Optional, Callable, List

from app.core.events import HiveEvent
from app.core.protocol import parse_p2p_handshake, parse_transfer_permit, parse_transfer_req

logger = logging.getLogger("hive.network")

BZZZ_MAGIC = 0x425A5A5A
PROTOCOL_VERSION = 0x01

CONTROL_PORT = 5000
P2P_PORT = 5001
MAX_PORT_OFFSET = 10

HEARTBEAT_INTERVAL_S = 2.0
HEARTBEAT_WEAK_S = 8.0
HEARTBEAT_DEAD_S = 20.0

MSG_DISCOVERY = 0x01
MSG_HOST_WELCOME = 0x02
MSG_HEARTBEAT = 0x03
MSG_P2P_REQ = 0x10
MSG_P2P_PERMIT = 0x11
MSG_P2P_HANDSHAKE = 0x20
MSG_P2P_ACK = 0x21
MSG_P2P_DATA = 0x30
MSG_P2P_DONE = 0x31
MSG_SH_RETIRE = 0x40

HEADER_FORMAT = "!IBBHI"
HEADER_SIZE = 12


async def _send_packet(
        writer: asyncio.StreamWriter,
        msg_type: int,
        payload: bytes) -> None:
    header = struct.pack(
        HEADER_FORMAT,
        BZZZ_MAGIC,
        PROTOCOL_VERSION,
        msg_type,
        0,
        len(payload))
    writer.write(header + payload)
    await writer.drain()


async def _recv_packet(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(HEADER_SIZE)
    magic, ver, msg_type, flags, size = struct.unpack(HEADER_FORMAT, header)
    if magic != BZZZ_MAGIC:
        raise ValueError(f"Invalid protocol magic: {hex(magic)}")
    payload = await reader.readexactly(size)
    return msg_type, payload


class NetworkManager:
    def __init__(
            self,
            node_uuid: str,
            node_name: str,
            score: int,
            pin: str,
            security,
            bus=None) -> None:
        self.node_uuid = node_uuid
        self.node_name = node_name
        self.score = score
        self.pin = pin
        self.security = security
        self.bus = bus
        self.local_ip = "0.0.0.0"
        self.control_port = CONTROL_PORT
        self.p2p_port = P2P_PORT
        self.peers: Dict[str, dict] = {}
        self.host_uuid: Optional[str] = None
        self.running = False
        self._control_server: Optional[asyncio.AbstractServer] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._discovery_recv_task: Optional[asyncio.Task] = None
        self._udp_sock: Optional[socket.socket] = None

        self.on_peer_joined: Optional[Callable] = None
        self.on_peer_left: Optional[Callable] = None
        self.on_host_elected: Optional[Callable] = None
        self.on_transfer_req: Optional[Callable] = None
        self.on_transfer_permit: Optional[Callable] = None
        self.on_p2p_handshake: Optional[Callable] = None
        self.on_p2p_done: Optional[Callable] = None
        self.on_host_lost: Optional[Callable] = None

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._host_writer: Optional[asyncio.StreamWriter] = None
        self._sweep_semaphore = asyncio.Semaphore(50)
        self._broadcast_tick = 0
        self.suppress_election_events = False
        self._rtt_samples: Dict[str, List[float]] = {}
        self._avg_rtt: Dict[str, float] = {}
        self._jitter: Dict[str, float] = {}
        self._hb_last_success: Dict[str, float] = {}
        self._hb_miss_count: Dict[str, int] = {}

    async def start(self, local_ip: str) -> None:
        if self.running and self.local_ip != "0.0.0.0":
            self.local_ip = local_ip
            return

        self.local_ip = local_ip

        async def _try_start_servers(p_ctrl):
            ctrl = await asyncio.start_server(self._handle_client, "0.0.0.0", p_ctrl)
            return ctrl

        if not self._control_server:
            for offset in range(MAX_PORT_OFFSET + 1):
                try:
                    self.control_port = CONTROL_PORT + offset
                    self.p2p_port = P2P_PORT + offset
                    self._control_server = await _try_start_servers(self.control_port)
                    break
                except OSError:
                    if offset == MAX_PORT_OFFSET:
                        raise RuntimeError("Could not find available ports")
                    continue

        if self.running:
             return 

        self.running = True
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._udp_sock.bind(("0.0.0.0", self.control_port))
        except Exception as e:
            logger.warning("Could not bind UDP discovery socket: %s", e)
        self._udp_sock.setblocking(False)
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._discovery_recv_task = asyncio.create_task(
            self._discovery_recv_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "[Network] Started on %s (control:%d)",
            local_ip,
            self.control_port)
        asyncio.create_task(self.active_scan())

    async def active_scan(self) -> None:
        if not self.local_ip or self.local_ip == "0.0.0.0":
            return
        logger.info(
            "[Network] Starting active BZZZ sweep on %s",
            self.local_ip)
        parts = self.local_ip.split(".")
        gateway = f"{parts[0]}.{parts[1]}.{parts[2]}.1"
        asyncio.create_task(self._probe_ip(gateway))
        tasks = []
        for i in range(1, 255):
            target = f"{parts[0]}.{parts[1]}.{parts[2]}.{i}"
            if target == self.local_ip or target == gateway:
                continue
            tasks.append(self._probe_ip(target))
        await asyncio.gather(*tasks)

    async def _probe_ip(self, ip: str) -> None:
        if not self.running:
            return
        async with self._sweep_semaphore:
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(ip, self.control_port), timeout=1.5)
                data = json.dumps(
                    {"uuid": self.node_uuid, "name": self.node_name, "score": self.score, "port": self.control_port}).encode()
                await _send_packet(w, MSG_DISCOVERY, self.security.encrypt(data))
                rt, rp = await asyncio.wait_for(_recv_packet(r), timeout=2.0)
                if rt == MSG_DISCOVERY:
                    self._process_discovery(json.loads(
                        self.security.decrypt(rp).decode()), ip, trace_id="SCAN")
                w.close()
                await w.wait_closed()
            except Exception:
                pass

    async def stop(self) -> None:
        self.running = False
        if self._discovery_task:
            self._discovery_task.cancel()
        if self._discovery_recv_task:
            self._discovery_recv_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._host_writer:
            self._host_writer.close()
            try:
                await self._host_writer.wait_closed()
            except Exception:
                pass
            self._host_writer = None
        if self._control_server:
            self._control_server.close()
            await self._control_server.wait_closed()
            self._control_server = None
        if self._udp_sock:
            self._udp_sock.close()
            self._udp_sock = None
        logger.info("[Network] Stopped")

    def _get_broadcast_addresses(self) -> List[str]:
        addrs = ["255.255.255.255"]
        try:
            for interface, snics in psutil.net_if_addrs().items():
                lower_if = interface.lower()
                if any(
                    x in lower_if for x in [
                        "loopback", "wsl", "veth", "docker", "br-", "virbr", "vpn"]):
                    continue
                stats = psutil.net_if_stats().get(interface)
                if stats and not stats.isup:
                    continue
                for snic in snics:
                    if snic.family == socket.AF_INET:
                        ip, mask = snic.address, snic.netmask
                        if ip.startswith("127."):
                            continue
                        try:
                            if mask:
                                network = ipaddress.IPv4Network(
                                    f"{ip}/{mask}", strict=False)
                                addrs.append(str(network.broadcast_address))
                            else:
                                parts = ip.split(".")
                                addrs.append(
                                    f"{parts[0]}.{parts[1]}.{parts[2]}.255")
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Broadcast discovery error: %s", e)
        unique_addrs = list(set(addrs))
        return unique_addrs

    async def _discovery_loop(self) -> None:
        if not self._udp_sock:
            return
        while self.running:
            try:
                trace_id = str(uuid.uuid4())[:8]
                data = json.dumps({
                    "uuid": self.node_uuid, 
                    "name": self.node_name, 
                    "score": self.score, 
                    "port": self.control_port,
                    "trace_id": trace_id
                }).encode()
                self._broadcast_tick += 1
                if self._broadcast_tick % 10 == 1:
                    logger.info("[Network] Broadcasting discovery")
                payload = self.security.encrypt(data)
                packet = struct.pack(
                    HEADER_FORMAT,
                    BZZZ_MAGIC,
                    PROTOCOL_VERSION,
                    MSG_DISCOVERY,
                    0,
                    len(payload)) + payload
                broadcast_ips = self._get_broadcast_addresses()
                for ip in broadcast_ips:
                    for offset in range(MAX_PORT_OFFSET + 1):
                        try:
                            self._udp_sock.sendto(packet, (ip, CONTROL_PORT + offset))
                        except Exception:
                            pass
                self._prune_stale_peers()
            except Exception:
                pass
            interval = 5.0 if len(self.peers) > 0 else 2.0
            await asyncio.sleep(interval)

    async def _discovery_recv_loop(self) -> None:
        if not self._udp_sock:
            return
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                packet, addr = await asyncio.wait_for(loop.sock_recvfrom(self._udp_sock, 65535), timeout=1.0)
                if len(packet) < HEADER_SIZE:
                    continue
                magic, ver, msg_type, flags, size = struct.unpack(
                    HEADER_FORMAT, packet[:HEADER_SIZE])
                if magic != BZZZ_MAGIC or len(packet) < HEADER_SIZE + size:
                    continue
                payload = packet[HEADER_SIZE: HEADER_SIZE + size]
                if msg_type != MSG_DISCOVERY:
                    continue
                data = json.loads(self.security.decrypt(payload).decode())
                trace_id = data.get("trace_id", "UDP-IN")
                self._process_discovery(data, addr[0], trace_id=trace_id)
            except asyncio.TimeoutError:
                continue
            except Exception:
                pass

    async def _handle_client(self, reader, writer) -> None:
        msg_type = None
        trace_id = "UNK"
        try:
            msg_type, payload = await _recv_packet(reader)
            data = json.loads(self.security.decrypt(payload).decode())
            trace_id = data.get("trace_id", str(uuid.uuid4())[:8])
            peer_ip = writer.get_extra_info("peername")[0]
            
            logger.debug("[Network][%s] TCP Client handler: msg_type=%d from %s", trace_id, msg_type, peer_ip)

            if msg_type == MSG_DISCOVERY:
                self._process_discovery(data, peer_ip, trace_id=trace_id)
            
            sender_uuid = data.get("uuid")
            if sender_uuid and sender_uuid in self.peers:
                self.peers[sender_uuid]["last_seen"] = time.time()
                self._hb_miss_count[sender_uuid] = 0
                self._update_peer_ui_state(sender_uuid, "green")

            if msg_type == MSG_P2P_REQ:
                req = parse_transfer_req(data)
                if self.on_transfer_req:
                    res = self.on_transfer_req(
                        {
                            "target_uuid": req.target_uuid,
                            "filename": req.file_meta.name,
                            "size": req.file_meta.size,
                            "sha256": req.file_meta.sha256,
                            "trace_id": trace_id},
                        writer)
                    if asyncio.iscoroutine(res): await res
            elif msg_type == MSG_P2P_PERMIT:
                permit = parse_transfer_permit(data)
                if self.on_transfer_permit:
                    res = self.on_transfer_permit(
                        {"target_ip": permit.target_ip, "target_port": permit.target_port, "trace_id": trace_id})
                    if asyncio.iscoroutine(res): await res
            elif msg_type == MSG_P2P_HANDSHAKE:
                handshake = parse_p2p_handshake(data)
                if self.on_p2p_handshake:
                    res = self.on_p2p_handshake(
                        {
                            "file_meta": {
                                "name": handshake.file_meta.name,
                                "size": handshake.file_meta.size,
                                "sha256": handshake.file_meta.sha256},
                            "challenge_nonce": handshake.challenge_nonce,
                            "trace_id": trace_id},
                        reader,
                        writer)
                    if asyncio.iscoroutine(res): await res
            elif msg_type == MSG_HEARTBEAT:
                logger.debug("[Network][%s] Heartbeat from %s", trace_id, sender_uuid)
            elif msg_type == MSG_SH_RETIRE:
                logger.info("[Network][%s] Session Host retired. Re-electing.", trace_id)
                self.host_uuid = None
                self._elect_host(trace_id=trace_id)
            elif msg_type == MSG_HOST_WELCOME:
                peers_list = data.get("peers", [])
                logger.info("[Network][%s] Received sync registry (%d peers)", trace_id, len(peers_list))
                for p in peers_list:
                    p_uid = p.get("uuid")
                    p_ip = p.get("ip")
                    if p_uid and p_uid != self.node_uuid and p_ip and p_ip != "0.0.0.0" and p_uid not in self.peers:
                        self.peers[p_uid] = {
                            "name": p.get("name"),
                            "score": p.get("score"),
                            "ip": p_ip,
                            "last_seen": time.time(),
                            "ui_state": "green"}
                        if self.on_peer_joined:
                            self.on_peer_joined(p_uid)
            elif msg_type == MSG_P2P_DONE:
                if self.on_p2p_done:
                    self.on_p2p_done(data.get("uuid"), trace_id=trace_id)
        except Exception as e:
            logger.debug("[Network][%s] Client handler error: %s", trace_id, e)
        finally:
            if msg_type not in (MSG_P2P_HANDSHAKE, MSG_P2P_DONE):
                try:
                    writer.close()
                except Exception:
                    pass

    async def _heartbeat_loop(self) -> None:
        while self.running:
            interval = HEARTBEAT_INTERVAL_S
            try:
                if self.host_uuid and self.host_uuid != self.node_uuid:
                    host_info = self.peers.get(self.host_uuid)
                    if host_info and host_info["ip"] != "0.0.0.0":
                        jitter = self._jitter.get(self.host_uuid, 0.0)
                        
                        dead_threshold = HEARTBEAT_DEAD_S
                        if jitter > 50.0:
                            interval = 5.0
                            dead_threshold = 30.0

                        try:
                            trace_id = str(uuid.uuid4())[:8]
                            start_ts = time.time()
                            r, w = await asyncio.wait_for(
                                asyncio.open_connection(host_info["ip"], host_info.get("port", self.control_port)), 
                                timeout=2.5)
                            data = {
                                "status": "ALIVE", 
                                "uuid": self.node_uuid, 
                                "timestamp": time.time(),
                                "trace_id": trace_id
                            }
                            await _send_packet(w, MSG_HEARTBEAT, self.security.encrypt(json.dumps(data).encode()))
                            w.close()
                            await w.wait_closed()
                            
                            now = time.time()
                            rtt = (now - start_ts) * 1000
                            self._update_rtt(self.host_uuid, rtt)
                            
                            self._hb_last_success[self.host_uuid] = now
                            self._hb_miss_count[self.host_uuid] = 0
                            self._update_peer_ui_state(self.host_uuid, "green")
                            
                        except Exception:
                            self._hb_miss_count[self.host_uuid] = self._hb_miss_count.get(self.host_uuid, 0) + 1
                            miss_count = self._hb_miss_count[self.host_uuid]
                            
                            if miss_count == 4:
                                logger.warning("[Network] Link WEAK. Firing deathbed probe.")
                                if await self._deathbed_probe(self.host_uuid):
                                    self._hb_miss_count[self.host_uuid] = 0
                                    self._update_peer_ui_state(self.host_uuid, "green")
                                    continue
                            
                            if miss_count >= 4:
                                self._update_peer_ui_state(self.host_uuid, "amber")

                            last_ok = self._hb_last_success.get(self.host_uuid, 0)
                            if time.time() - last_ok >= dead_threshold:
                                if self.on_host_lost:
                                    self.on_host_lost(self.host_uuid)
            except Exception:
                pass
                
            stagger = (abs(hash(self.node_uuid)) % 5) * 0.1
            await asyncio.sleep(interval + stagger)

    async def _deathbed_probe(self, peer_uuid: str) -> bool:
        peer = self.peers.get(peer_uuid)
        if not peer: return False
        for _ in range(4):
            try:
                _, w = await asyncio.wait_for(
                    asyncio.open_connection(peer["ip"], peer.get("port", self.control_port)),
                    timeout=0.5)
                w.close()
                await w.wait_closed()
                return True
            except Exception:
                await asyncio.sleep(0.5)
        return False

    def _update_peer_ui_state(self, uid: str, state: str) -> None:
        peer = self.peers.get(uid)
        if peer and peer.get("ui_state") != state:
            peer["ui_state"] = state
            if self.bus:
                self.bus.publish(HiveEvent.PEER_STATE_CHANGED, {"uuid": uid, "state": state})

    def _update_rtt(self, uid: str, rtt: float) -> None:
        samples = self._rtt_samples.get(uid, [])
        samples.append(rtt)
        if len(samples) > 10:
            samples.pop(0)
        self._rtt_samples[uid] = samples
        self._avg_rtt[uid] = sum(samples) / len(samples)
        
        if len(samples) >= 2:
            self._jitter[uid] = statistics.stdev(samples)
        else:
            self._jitter[uid] = 0.0
        
        if self.bus:
            self.bus.publish(HiveEvent.HEARTBEAT_METRICS, {
                "peer_uuid": uid,
                "rtt_ms": rtt,
                "avg_rtt_ms": self._avg_rtt[uid],
                "jitter_ms": self._jitter.get(uid, 0.0)
            })

    def _process_discovery(self, data: dict, ip: str, trace_id: str = "AUTO") -> None:
        uid = data.get("uuid")
        if not uid or uid == self.node_uuid or not ip or ip == "0.0.0.0":
            return
        
        port = data.get("port", CONTROL_PORT)
        is_new = uid not in self.peers
        peer_data = {
            "name": data.get("name"),
            "score": data.get("score"),
            "ip": ip,
            "port": port,
            "last_seen": time.time(),
            "ui_state": "green"
        }

        if is_new:
            logger.info("[Network][%s] New peer discovered: %s (%s)", trace_id, data.get("name"), ip)
            self.peers[uid] = peer_data
            if self.on_peer_joined:
                self.on_peer_joined(uid)
            if self.bus:
                self.bus.publish(HiveEvent.PEER_DISCOVERED, uid)
            if self.host_uuid == self.node_uuid:
                asyncio.create_task(self.send_host_welcome(ip, trace_id=trace_id))
        else:
            self.peers[uid].update(peer_data)
        self._elect_host(trace_id=trace_id)

    def _prune_stale_peers(self) -> None:
        jitter = max(self._jitter.values()) if self._jitter else 0
        dead_threshold = 30.0 if jitter > 50.0 else HEARTBEAT_DEAD_S
        cutoff = time.time() - dead_threshold
        removed = [uid for uid, peer in self.peers.items() if peer.get("last_seen", 0) < cutoff]
        for uid in removed:
            peer_name = self.peers[uid].get("name", "Unknown")
            logger.info("[Network] Peer stale, removing: %s", peer_name)
            self.peers.pop(uid, None)
            if self.on_peer_left:
                self.on_peer_left(uid)
            if self.bus:
                self.bus.publish(HiveEvent.PEER_LEFT, uid)
        if removed:
            self._elect_host(trace_id="PRUNE")

    def update_vitality(self, score: int) -> None:
        self.score = score
        self._elect_host(trace_id="VITALITY")

    def _elect_host(self, trace_id: str = "ELECTION") -> None:
        all_nodes = [(self.node_uuid, self.score)] + [
            (u, p.get("score") or 0) for u, p in self.peers.items()
        ]
        best_uid = max(all_nodes, key=lambda x: (x[1], x[0]))[0]
        if best_uid != self.host_uuid:
            old_host = self.host_uuid
            self.host_uuid = best_uid
            if self.suppress_election_events:
                return
            logger.info("[Network][%s] Host election changed: %s -> %s", trace_id, old_host, best_uid)
            if self.on_host_elected:
                self.on_host_elected(best_uid)
            if self.bus:
                self.bus.publish(HiveEvent.HOST_ELECTED, best_uid)

    async def send_transfer_req(
            self,
            target_uuid: str,
            filename: str,
            size: int,
            sha: str,
            trace_id: str = "TX-REQ") -> None:
        peer = self.peers.get(target_uuid)
        if not peer:
            return
        try:
            logger.info("[Network][%s] Requesting transfer of '%s' to %s", trace_id, filename, peer["name"])
            r, w = await asyncio.open_connection(peer["ip"], peer.get("port", self.control_port))
            data = {
                "target_uuid": target_uuid,
                "filename": filename,
                "size": size,
                "sha256": sha,
                "trace_id": trace_id}
            await _send_packet(w, MSG_P2P_REQ, self.security.encrypt(json.dumps(data).encode()))
            rt, rp = await asyncio.wait_for(_recv_packet(r), timeout=15.0)
            if rt == MSG_P2P_PERMIT:
                permit_data = json.loads(self.security.decrypt(rp).decode())
                permit = parse_transfer_permit(permit_data)
                logger.info("[Network][%s] Received permit for transfer", trace_id)
                if self.on_transfer_permit:
                    self.on_transfer_permit(
                        {"target_ip": peer["ip"], "target_port": permit.target_port, "trace_id": trace_id})
            w.close()
        except Exception as e:
            logger.error("[Network][%s] Failed to send transfer request: %s", trace_id, e)

    async def send_transfer_permit(
            self,
            writer,
            target_ip: str,
            target_port: int,
            trace_id: str = "TX-PERMIT") -> None:
        data = {"target_ip": target_ip, "target_port": target_port, "trace_id": trace_id}
        logger.info("[Network][%s] Sending transfer permit to %s:%d", trace_id, target_ip, target_port)
        await _send_packet(writer, MSG_P2P_PERMIT, self.security.encrypt(json.dumps(data).encode()))
        writer.close()

    async def send_p2p_handshake(
            self,
            writer,
            filename: str,
            size: int,
            sha: str,
            challenge_nonce: str,
            trace_id: str = "P2P-HS") -> None:
        data = {
            "file_meta": {
                "name": filename,
                "size": size,
                "sha256": sha},
            "challenge_nonce": challenge_nonce,
            "trace_id": trace_id}
        logger.info("[Network][%s] Sending P2P handshake for '%s'", trace_id, filename)
        await _send_packet(writer, MSG_P2P_HANDSHAKE, self.security.encrypt(json.dumps(data).encode()))

    async def send_p2p_ack(
            self,
            writer,
            resume_offset: int,
            signature: str,
            trace_id: str = "P2P-ACK") -> None:
        data = {"resume_offset": resume_offset, "signature": signature, "trace_id": trace_id}
        logger.info("[Network][%s] Sending P2P ACK (resume: %d)", trace_id, resume_offset)
        await _send_packet(writer, MSG_P2P_ACK, self.security.encrypt(json.dumps(data).encode()))

    async def send_p2p_done(self, target_ip: str, target_port: int, trace_id: str = "P2P-DONE") -> None:
        try:
            logger.info("[Network][%s] Notifying peer transfer complete", trace_id)
            _, w = await asyncio.wait_for(asyncio.open_connection(target_ip, target_port), timeout=5.0)
            data = {"status": "DONE", "uuid": self.node_uuid, "trace_id": trace_id}
            await _send_packet(w, MSG_P2P_DONE, self.security.encrypt(json.dumps(data).encode()))
            w.close()
            await w.wait_closed()
        except Exception as e:
            logger.debug("[Network][%s] Failed to send P2P_DONE: %s", trace_id, e)

    async def send_host_welcome(self, target_ip: str, trace_id: str = "WELCOME") -> None:
        if not self.running:
            return
        logger.info("[Network][%s] Sending sync registry to %s", trace_id, target_ip)
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(target_ip, self.control_port), timeout=3.0)
            reg = [{"uuid": u, "name": p["name"], "score": p["score"],
                    "ip": p["ip"]} for u, p in self.peers.items()]
            reg.append({"uuid": self.node_uuid,
                        "name": self.node_name,
                        "score": self.score,
                        "ip": self.local_ip})
            data = {"peers": reg, "trace_id": trace_id}
            await _send_packet(w, MSG_HOST_WELCOME, self.security.encrypt(json.dumps(data).encode()))
            w.close()
            await w.wait_closed()
        except Exception as e:
            logger.debug("[Network][%s] Failed to send welcome to %s: %s", trace_id, target_ip, e)

    async def broadcast_retirement(self) -> None:
        trace_id = str(uuid.uuid4())[:8]
        logger.info("[Network][%s] Node retiring. Notifying %d peers.", trace_id, len(self.peers))
        for uid, peer in list(self.peers.items()):
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(peer["ip"], self.control_port), timeout=2.0)
                data = {"reason": "exit", "trace_id": trace_id}
                await _send_packet(w, MSG_SH_RETIRE, self.security.encrypt(json.dumps(data).encode()))
                w.close()
                await w.wait_closed()
            except Exception:
                pass

    def decrypt_payload(self, payload: bytes) -> bytes:
        return self.security.decrypt(payload)

import asyncio
import json
import logging
import os
import uuid

from app.core.data_plane import DataPlane
from app.core.events import HiveEvent
from app.core.network import MSG_P2P_ACK, P2P_PORT, _recv_packet
from app.core.protocol import parse_p2p_handshake
from app.core.utils import sanitize_receive_filename

logger = logging.getLogger("hive.transfer")


class TransferController:
    def __init__(self, owner) -> None:
        self._owner = owner

    def send_file(self, path: str, target_name: str) -> None:
        owner = self._owner
        owner._submit(owner._start_file_send(path, target_name))

    async def on_transfer_req(self, data: dict, writer) -> None:
        owner = self._owner
        trace_id = data.get("trace_id", "TX-IN")
        if not owner.network:
            if writer:
                writer.close()
            return
        requester_ip = writer.get_extra_info("peername")[0] if writer else ""
        if requester_ip:
            owner.bus.publish(HiveEvent.INCOMING_TRANSFER, data.get("size", 0), trace_id=trace_id)
            await owner.network.send_transfer_permit(writer, requester_ip, owner.network.p2p_port, trace_id=trace_id)

    def on_transfer_permit(self, data: dict) -> None:
        owner = self._owner
        trace_id = data.get("trace_id", "TX-PRMT")
        if owner._pending_send:
            fallback_port = owner.network.p2p_port if owner.network else P2P_PORT
            owner._submit(
                owner._execute_p2p_send(
                    data.get("target_ip", ""),
                    data.get("target_port", fallback_port),
                    owner._pending_send,
                    trace_id=trace_id
                )
            )

    async def execute_p2p_send(self, ip: str, port: int, pending: dict, trace_id: str = "P2P-SEND") -> None:
        owner = self._owner
        async with owner._transfer_lock:
            owner._active_transfer_task = asyncio.current_task()
            writer = None
            try:
                if not owner.network or not owner.dp:
                    raise RuntimeError("Network/DataPlane not ready")

                challenge_nonce = os.urandom(8).hex()
                target_port = owner.network.control_port if owner.network else 5000
                for uid, info in owner.network.peers.items():
                    if uid == owner._target_peer_uuid:
                        target_port = info.get("port", target_port)
                        break

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, target_port), timeout=10.0
                )
                await owner.network.send_p2p_handshake(
                    writer,
                    pending["filename"],
                    pending["file_size"],
                    pending["sha256"],
                    challenge_nonce,
                    trace_id=trace_id
                )
                msg_type, payload = await asyncio.wait_for(_recv_packet(reader), timeout=30.0)

                if msg_type != MSG_P2P_ACK:
                    raise ValueError(f"Expected P2P_ACK, got type {msg_type}")

                ack_data = json.loads(owner.network.decrypt_payload(payload).decode())
                signature = ack_data.get("signature")

                if signature == "ALREADY_COMPLETE":
                    logger.info("[DataPlane][%s] Peer already has complete file: %s", trace_id, pending["filename"])
                    owner.bus.publish(
                        HiveEvent.TRANSFER_PROGRESS,
                        {"current": pending["file_size"], "total": pending["file_size"]}
                    )
                    owner.bus.publish(HiveEvent.SEND_COMPLETE, None)
                    if writer:
                        writer.close()
                    return

                sig_decrypted = json.loads(
                    owner.security.decrypt(bytes.fromhex(signature)).decode()
                )
                if not (
                    sig_decrypted.get("nonce") == challenge_nonce
                    and sig_decrypted.get("uuid") == owner._target_peer_uuid
                ):
                    raise ValueError("Identity Mismatch")

                resume_offset = ack_data.get("resume_offset", 0)

                if writer:
                    writer.close()
                writer = None

                try:
                    await owner.dp.disconnect()
                except OSError:
                    pass

                await owner._send_agent_command({"type": "STOP_DATA_PLANE", "trace_id": trace_id})
                await asyncio.sleep(0.5)
                await owner._send_agent_command(
                    {"type": "START_DATA_PLANE", "peer_ip": ip, "peer_port": port, "trace_id": trace_id}
                )

                for _ in range(30):
                    if owner.dp and owner.dp._connected:
                        break
                    await asyncio.sleep(0.2)

                if not owner.dp or not owner.dp._connected:
                    raise RuntimeError("Failed to connect to agent data plane bridge")

                await asyncio.sleep(0.2)

                logger.info(
                    "[DataPlane][%s] Starting file send: %s (%d bytes)",
                    trace_id,
                    pending["filename"],
                    pending["file_size"],
                )

                owner._transfer_done_fut = owner._loop.create_future()

                await owner.dp.send_file(
                    pending["file_path"], resume_offset=resume_offset, progress_cb=owner._on_progress
                )

                logger.info("[DataPlane][%s] Bytes streamed, awaiting receiver confirmation...", trace_id)
                try:
                    await asyncio.wait_for(owner._transfer_done_fut, timeout=15.0)
                    logger.info(
                        "[DataPlane][%s] Send complete: %s (Confirmed by Peer)", trace_id, pending["filename"]
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[DataPlane][%s] Send finished but Peer confirmation timed out.", trace_id
                    )

                owner.bus.publish(HiveEvent.SEND_COMPLETE, None)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataPlane][%s] Exception in P2P send: %s", trace_id, repr(e))
                owner.bus.publish(HiveEvent.TRANSFER_ERROR, str(e))
            finally:
                if writer:
                    try:
                        writer.close()
                    except Exception:
                        pass
                owner._pending_send = None
                owner._active_transfer_task = None
                await owner._reset_data_plane()

    async def on_p2p_handshake(self, data: dict, reader, writer) -> None:
        await self.execute_p2p_receive(data, reader, writer)

    async def execute_p2p_receive(self, data: dict, reader, writer) -> None:
        owner = self._owner
        trace_id = data.get("trace_id", "P2P-RECV")
        async with owner._transfer_lock:
            owner._active_transfer_task = asyncio.current_task()
            if not owner.network or not owner.dp:
                owner.bus.publish(HiveEvent.TRANSFER_ERROR, "Network/DataPlane not ready")
                owner._active_transfer_task = None
                return
            try:
                handshake = parse_p2p_handshake(data)
                name = sanitize_receive_filename(handshake.file_meta.name)
                dest = os.path.join(owner.download_dir, name)
                resume_offset = 0
                if os.path.exists(dest):
                    existing_size = os.path.getsize(dest)
                    if existing_size < handshake.file_meta.size:
                        res_fut = owner._loop.create_future()
                        owner._ui_call_with_future(
                            res_fut,
                            "confirm_resume",
                            name,
                            existing_size,
                            handshake.file_meta.size,
                        )
                        if await res_fut:
                            resume_offset = existing_size
                        else:
                            os.remove(dest)
                    elif existing_size == handshake.file_meta.size:
                        await owner.network.send_p2p_ack(writer, existing_size, "ALREADY_COMPLETE", trace_id=trace_id)
                        owner.bus.publish(HiveEvent.RECEIVE_COMPLETE, None)
                        return
                sig_raw = json.dumps(
                    {"nonce": handshake.challenge_nonce, "uuid": owner.my_uuid}
                ).encode()
                signature = owner.security.encrypt(sig_raw).hex()
                await owner.network.send_p2p_ack(writer, resume_offset, signature, trace_id=trace_id)

                logger.info(
                    "[DataPlane][%s] Receiving file: %s (%d bytes)", trace_id, name, handshake.file_meta.size
                )
                await owner.dp.receive_file(
                    dest, handshake.file_meta.size, resume_offset=resume_offset, progress_cb=owner._on_progress
                )

                peer_ip = writer.get_extra_info("peername")[0]
                target_port = 5000
                for _, info in owner.network.peers.items():
                    if info.get("ip") == peer_ip:
                        target_port = info.get("port", 5000)
                        break

                await owner.network.send_p2p_done(peer_ip, target_port, trace_id=trace_id)

                logger.info("[DataPlane][%s] Receive complete: %s", trace_id, name)
                owner.bus.publish(HiveEvent.RECEIVE_COMPLETE, None)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataPlane][%s] Exception in P2P receive: %s", trace_id, repr(e))
                owner.bus.publish(HiveEvent.TRANSFER_ERROR, str(e))
            finally:
                owner._active_transfer_task = None
                if not (owner.dp and owner.dp._connected):
                    await owner._reset_data_plane()

    async def reset_data_plane(self, trace_id="TX-RESET") -> None:
        owner = self._owner
        try:
            if owner.dp:
                await owner.dp.disconnect()
        except OSError:
            pass
        owner.dp = None
        await owner._send_agent_command({"type": "STOP_DATA_PLANE", "trace_id": trace_id})
        await asyncio.sleep(0.3)
        if owner._connection_mode != "IDLE" and owner._running:
            await owner._send_agent_command(
                {
                    "type": "START_DATA_PLANE",
                    "peer_port": owner.network.p2p_port if owner.network else P2P_PORT,
                    "trace_id": trace_id
                }
            )

    def on_p2p_done(self, uid: str, trace_id: str = "TX-DONE") -> None:
        owner = self._owner
        logger.info("[Network][%s] Received P2P_DONE from peer", trace_id)
        if hasattr(owner, "_transfer_done_fut") and not owner._transfer_done_fut.done():
            owner._transfer_done_fut.set_result(True)

    async def start_file_send(self, path: str, target: str) -> None:
        owner = self._owner
        if not owner.network:
            return
        if owner._pending_send is not None:
            owner.bus.publish(HiveEvent.TRANSFER_ERROR, "A transfer is already in progress.")
            return
        uid = next((u for u, i in owner.network.peers.items() if i.get("name") == target), None)
        if not uid:
            return
        
        trace_id = str(uuid.uuid4())[:8]
        owner._target_peer_uuid = uid
        owner._pending_send = {
            "file_path": path,
            "filename": os.path.basename(path),
            "file_size": os.path.getsize(path),
            "sha256": await owner._loop.run_in_executor(None, DataPlane.compute_sha256, path),
            "trace_id": trace_id
        }
        await owner.network.send_transfer_req(
            uid,
            owner._pending_send["filename"],
            owner._pending_send["file_size"],
            owner._pending_send["sha256"],
            trace_id=trace_id
        )
        owner._submit(owner._clear_pending_send_after_timeout(owner._pending_send))

    async def clear_pending_send_after_timeout(self, pending_obj: dict) -> None:
        owner = self._owner
        await asyncio.sleep(15)
        if owner._pending_send is pending_obj and not owner._transfer_lock.locked():
            owner._pending_send = None
            owner.bus.publish(HiveEvent.TRANSFER_ERROR, "Transfer request timed out.")

    def on_progress(self, current: int, total: int) -> None:
        self._owner.bus.publish(
            HiveEvent.TRANSFER_PROGRESS,
            {"current": current, "total": total}
        )

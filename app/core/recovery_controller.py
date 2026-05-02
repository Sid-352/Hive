import asyncio
import logging
import time
import uuid

from app.core.agent import AsyncHardwareAgent
from app.core.events import HiveEvent

logger = logging.getLogger("hive.recovery")


class RecoveryController:
    def __init__(self, owner) -> None:
        self._owner = owner

    async def watchdog_loop(self) -> None:
        owner = self._owner
        while owner._running:
            await asyncio.sleep(5)
            if not owner.agent.running or (time.time() - owner._last_telemetry_time) > 15:
                trace_id = str(uuid.uuid4())[:8]
                logger.critical("[Recovery][%s] Watchdog detected agent failure. Initiating recovery...", trace_id)
                owner._recovery_task = asyncio.create_task(owner._recover_agent(trace_id=trace_id))
                break
            try:
                await owner._send_agent_command({"type": "GET_TELEMETRY"})
            except Exception as e:
                logger.warning("[Recovery] Watchdog heartbeat command failed: %s", e)

    async def recover_agent(self, trace_id: str = "REC-AUTO") -> None:
        owner = self._owner
        owner.bus.publish(HiveEvent.STATUS_CHANGED, "RECOVERING AGENT...")
        logger.info("[Recovery][%s] Restarting hardware agent process", trace_id)
        if owner._dispatcher_task:
            owner._dispatcher_task.cancel()
        if owner._watchdog_task:
            owner._watchdog_task.cancel()
        await owner.agent.stop()

        owner.agent = AsyncHardwareAgent(executable_path=owner.agent._exe_path)
        try:
            await owner.agent.start()
            owner._dispatcher_generation += 1
            owner._dispatcher_task = asyncio.create_task(
                owner._dispatch_agent_events(owner._dispatcher_generation)
            )
            owner._last_telemetry_time = time.time()
            if owner._watchdog_task and not owner._watchdog_task.done():
                owner._watchdog_task.cancel()
            owner._watchdog_task = asyncio.create_task(owner._watchdog_loop())
            owner.bus.publish(HiveEvent.STATUS_CHANGED, "AGENT READY")

            if owner._intended_state == "HOST":
                owner.host_group()
            elif owner._intended_state == "CLIENT" and owner._target_uuid:
                owner.join_group(owner._target_uuid)

        except Exception as e:
            logger.error("[Recovery][%s] Agent recovery failed: %s", trace_id, e)
            owner.bus.publish(HiveEvent.STATUS_CHANGED, f"RECOVERY FAILED: {e}")

    async def auto_recovery_loop(self) -> None:
        owner = self._owner
        retries, backoff = 0, 2
        while owner._intended_state in ("HOST", "CLIENT") and retries < 8:
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
            if owner._intended_state == "IDLE":
                break
            if owner.network and owner.network.running:
                break
            try:
                if owner._intended_state == "HOST":
                    await owner._send_agent_command(
                        {"type": "CREATE_GROUP", "device_id": owner.my_name[:8].upper()}
                    )
                elif owner._intended_state == "CLIENT" and owner._target_uuid:
                    await owner._send_agent_command({"type": "CONNECT", "uuid": owner._target_uuid})
            except Exception:
                pass
            retries += 1
            backoff = min(backoff * 2, 30)

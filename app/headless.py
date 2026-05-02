import asyncio
import json
import logging
import sys
import argparse
from typing import Any, Dict, List

from app.core.controller import AppController
from app.core.events import HiveEvent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("hive.drone")

class DaemonStateTracker:
    def __init__(self, bus):
        self.state = {
            "status": "IDLE",
            "network_state": "OFFLINE",
            "swarm_role": "NONE",
            "vitality_score": 0,
            "peers": [],
            "transfer": {"active": False, "progress": 0, "total": 0, "error": None}
        }
        bus.subscribe(HiveEvent.STATUS_CHANGED, self._on_status)
        bus.subscribe(HiveEvent.NETWORK_STATE_CHANGED, self._on_net_state)
        bus.subscribe(HiveEvent.SWARM_ROLE_CHANGED, self._on_role)
        bus.subscribe(HiveEvent.TELEMETRY_UPDATED, self._on_telemetry)
        bus.subscribe(HiveEvent.SESSION_PEERS_UPDATED, self._on_peers)
        bus.subscribe(HiveEvent.TRANSFER_PROGRESS, self._on_progress)
        bus.subscribe(HiveEvent.TRANSFER_ERROR, self._on_error)
        bus.subscribe(HiveEvent.SEND_COMPLETE, self._on_transfer_done)
        bus.subscribe(HiveEvent.RECEIVE_COMPLETE, self._on_transfer_done)

    def _on_status(self, e, data): self.state["status"] = str(data)
    def _on_net_state(self, e, data): self.state["network_state"] = str(data)
    def _on_role(self, e, data): self.state["swarm_role"] = str(data)
    def _on_telemetry(self, e, data): self.state["vitality_score"] = data.get("vitality_score", 0)
    def _on_peers(self, e, data): self.state["peers"] = data
    def _on_progress(self, e, data): self.state["transfer"].update({"active": True, "progress": data["current"], "total": data["total"], "error": None})
    def _on_error(self, e, data): self.state["transfer"].update({"active": False, "error": str(data)})
    def _on_transfer_done(self, e, data): self.state["transfer"]["active"] = False

class HiveDroneAPI:
    def __init__(self, ctrl: AppController, tracker: DaemonStateTracker, host="127.0.0.1", port=5050):
        self.ctrl = ctrl
        self.tracker = tracker
        self.host = host
        self.port = port

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info(f"Drone API listening on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader, writer):
        try:
            data = await reader.read(4096)
            if not data: return
            request = json.loads(data.decode())
            cmd = request.get("cmd")
            response = {"status": "error", "message": "Unknown command"}
            if cmd == "status": response = {"status": "success", "data": self.tracker.state}
            elif cmd == "scan":
                self.ctrl.scan_groups()
                response = {"status": "success", "message": "Scan started"}
            elif cmd == "host":
                self.ctrl.host_group(r=request.get("ruthless", False))
                response = {"status": "success", "message": "Hosting swarm"}
            elif cmd == "join":
                u = request.get("uuid")
                if u: self.ctrl.join_group(u); response = {"status": "success", "message": "Joining"}
                else: response = {"message": "Missing uuid"}
            elif cmd == "send":
                p, t = request.get("path"), request.get("target")
                if p and t: self.ctrl.send_file(p, t); response = {"status": "success", "message": "Sending"}
                else: response = {"message": "Missing path or target"}
            elif cmd == "leave":
                self.ctrl.leave_session()
                response = {"status": "success", "message": "Leaving"}
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except Exception as e: logger.error(f"API Error: {e}")
        finally:
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass

async def main():
    parser = argparse.ArgumentParser(description="Hive Drone")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()

    ctrl = AppController(room_pin="0000", agent_override=None, debug=False)
    tracker = DaemonStateTracker(ctrl.bus)
    api = HiveDroneAPI(ctrl, tracker, port=args.port)

    try:
        # AppController.start() is sync and starts its own loop thread
        ctrl.start()
        await api.start()
    except KeyboardInterrupt: pass
    finally:
        ctrl.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

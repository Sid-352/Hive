import argparse
import logging
import sys
import asyncio
import os
import ctypes
from typing import Optional

from app.core.security import DEFAULT_ROOM_PIN
from app.core.utils import sanitize_receive_filename
from app.core.agent import AsyncHardwareAgent, _resolve_executable


logger = logging.getLogger("hive.main")


async def run_inspector(agent_override: Optional[str]) -> None:
    print("=== Hive Inspector Diagnostic ===")

    is_admin = False
    try:
        if sys.platform == "win32":
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            is_admin = os.getuid() == 0
    except Exception:
        pass

    status = "[OK]" if is_admin else "[WARN]"
    print(f"{status} Privileges: {'Administrator' if is_admin else 'Standard User'}")
    if not is_admin:
        print("       Note: WiFi Direct operations usually require Admin/Root.")

    try:
        exe = _resolve_executable(agent_override)
        print(f"[OK] Agent Binary: {exe}")
    except Exception as e:
        print(f"[FAIL] Agent Binary: {e}")
        return

    agent = AsyncHardwareAgent(executable_path=agent_override)
    print("      Attempting to launch hardware agent...")
    try:
        await asyncio.wait_for(agent.start(), timeout=10.0)
        print(f"[OK] Agent Connectivity: Responded READY (v{agent.version})")

        await agent.send_command({"type": "GET_TELEMETRY"})
        telemetry = await asyncio.wait_for(agent.response_queue.get(), timeout=5.0)
        if telemetry.get("type") == "TELEMETRY":
            score = telemetry.get("vitality_score", 0)
            print(
                f"[OK] Hardware Telemetry: Received (Vitality Score: {score})")
        else:
            print(
                f"[WARN] Hardware Telemetry: Unexpected response: {telemetry}")

        await agent.stop()
    except Exception as e:
        print(f"[FAIL] Agent Connectivity: {e}")

    print("\nDiagnostic complete.")


def _sanitize_receive_filename(filename: Optional[str]) -> str:
    return sanitize_receive_filename(filename)


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.StreamHandler(sys.stderr)]
    
    try:
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            log_dir = os.path.join(exe_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "hive.log")
            handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))
            print(f"[*] Persistent logging to: {log_file}")
    except Exception as e:
        print(f"[*] Warning: Could not initialize file logging: {e}")

    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _preflight_firewall() -> bool:
    if sys.platform != "win32":
        return True
        
    from app.core.firewall import check_firewall_rules, setup_firewall_elevated
    if not check_firewall_rules():
        from PySide6.QtWidgets import QMessageBox, QApplication
        _ = QApplication.instance() or QApplication(sys.argv)
        ret = QMessageBox.question(
            None, "Firewall Configuration",
            "Hive requires firewall rules to communicate with peers.\n\n"
            "Would you like to configure them now? (Requires Administrator privileges)",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            setup_firewall_elevated()
            import time
            time.sleep(1)
            return True
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Hive P2P File Transfer")
    parser.add_argument(
        "--mock",
        metavar="PATH",
        default=None,
        help="Path to a mock agent binary for offline development.")
    parser.add_argument(
        "--pin",
        default=DEFAULT_ROOM_PIN,
        help=f"Room passphrase for session encryption (default: {DEFAULT_ROOM_PIN}).")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Set log level to DEBUG.")
    parser.add_argument(
        "--inspector",
        action="store_true",
        help="Run system diagnostics and exit.")
    args = parser.parse_args()

    if args.inspector:
        asyncio.run(run_inspector(args.mock))
        return

    from PySide6.QtWidgets import QApplication
    from app.core.controller import AppController
    from app.ui.app import HiveMainWindow
    from app.ui.theme import get_stylesheet

    _configure_logging(args.debug)
    
    _preflight_firewall()

    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())

    controller = AppController(
        room_pin=args.pin,
        agent_override=args.mock,
        debug=args.debug)
    
    window = HiveMainWindow(controller)
    controller.start()
    
    window.show()
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    finally:
        controller.shutdown()


if __name__ == "__main__":
    main()

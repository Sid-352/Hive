import os
import sys
import subprocess
import logging
import ctypes

logger = logging.getLogger("hive.firewall")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def check_firewall_rules():
    if sys.platform != "win32":
        return True
        
    try:
        res = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=Hive Core (App Bound)"],
            capture_output=True, text=True
        )
        return res.returncode == 0
    except Exception:
        return False

def setup_firewall_elevated():
    if sys.platform != "win32":
        return
        
    script_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "setup-hive.ps1"))
    
    if not os.path.exists(script_path):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist_tools", "setup-hive.ps1"))

    if not os.path.exists(script_path):
        logger.error(f"Firewall setup script not found at {script_path}")
        return False

    logger.info("Requesting elevation for firewall configuration...")
    
    try:
        params = f"-NoProfile -ExecutionPolicy Bypass -File \"{script_path}\""
        ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 1)
        return True
    except Exception as e:
        logger.error(f"Failed to trigger elevated firewall setup: {e}")
        return False

import threading
from PySide6.QtCore import QObject, Signal

class QtSignalBus(QObject):
    status_changed = Signal(str)
    telemetry_updated = Signal(dict)
    
    groups_discovered = Signal(list)
    
    peers_updated = Signal(list)
    peer_state_changed = Signal(dict)
    network_state_changed = Signal(str)
    swarm_role_changed = Signal(str)
    
    transfer_progress = Signal(int, int)
    transfer_error = Signal(str)
    send_complete = Signal()
    receive_complete = Signal()
    incoming_transfer = Signal(int)
    log_message = Signal(str)
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

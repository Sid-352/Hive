from app.core.events import HiveEvent


class UiEventAdapter:
    def __init__(self, window, bus) -> None:
        self._window = window
        self._bus = bus

        bus.subscribe(HiveEvent.STATUS_CHANGED, self._on_status)
        bus.subscribe(HiveEvent.TELEMETRY_UPDATED, self._on_telemetry)
        bus.subscribe(HiveEvent.DISCOVERY_GROUPS_UPDATED, self._on_discovery_groups)
        bus.subscribe(HiveEvent.NETWORK_STATE_CHANGED, self._on_network_state)
        bus.subscribe(HiveEvent.SWARM_ROLE_CHANGED, self._on_swarm_role)
        bus.subscribe(HiveEvent.PEER_STATE_CHANGED, self._on_peer_state)
        bus.subscribe(HiveEvent.SESSION_PEERS_UPDATED, self._on_session_peers)
        bus.subscribe(HiveEvent.TRANSFER_TARGETS_UPDATED, self._on_transfer_targets)
        bus.subscribe(HiveEvent.DATA_PLANE_STATE_CHANGED, self._on_data_plane_state)
        bus.subscribe(HiveEvent.TRANSFER_PROGRESS, self._on_transfer_progress)
        bus.subscribe(HiveEvent.TRANSFER_ERROR, self._on_transfer_error)
        bus.subscribe(HiveEvent.SEND_COMPLETE, self._on_send_complete)
        bus.subscribe(HiveEvent.RECEIVE_COMPLETE, self._on_receive_complete)
        bus.subscribe(HiveEvent.INCOMING_TRANSFER, self._on_incoming_transfer)
        bus.subscribe(HiveEvent.SHOW_SCREEN, self._on_show_screen)

    def _on_status(self, event, data) -> None:
        self._window.update_status(str(data))

    def _on_telemetry(self, event, data) -> None:
        if not isinstance(data, dict):
            return
        self._window.bus.telemetry_updated.emit(data)
        self._window.set_vitality(data.get("vitality_score", 0))
        self._window.telemetry_pulse()

    def _on_discovery_groups(self, event, data) -> None:
        groups = data if isinstance(data, list) else []
        self._window.set_discovery_groups(groups)

    def _on_network_state(self, event, data) -> None:
        self._window.set_network_state(str(data))

    def _on_swarm_role(self, event, data) -> None:
        self._window.set_swarm_role(str(data))

    def _on_peer_state(self, event, data) -> None:
        if isinstance(data, dict):
            self._window.bus.peer_state_changed.emit(data)

    def _on_session_peers(self, event, data) -> None:
        peers = data if isinstance(data, list) else []
        self._window.set_session_peers(peers)

    def _on_transfer_targets(self, event, data) -> None:
        peers = data if isinstance(data, list) else []
        self._window.set_transfer_targets(peers)

    def _on_data_plane_state(self, event, data) -> None:
        self._window.set_data_plane_state(bool(data))

    def _on_transfer_progress(self, event, data) -> None:
        if not isinstance(data, dict):
            return
        self._window.update_transfer_progress(data.get("current", 0), data.get("total", 1))

    def _on_transfer_error(self, event, data) -> None:
        self._window.report_transfer_error(str(data))

    def _on_send_complete(self, event, data) -> None:
        self._window.send_complete()

    def _on_receive_complete(self, event, data) -> None:
        self._window.receive_complete()

    def _on_incoming_transfer(self, event, data) -> None:
        self._window.mark_received(int(data))

    def _on_show_screen(self, event, data) -> None:
        name = str(data).lower()
        self._window.show_screen(name)

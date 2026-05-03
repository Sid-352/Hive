import asyncio
import logging
import time
import weakref
from enum import Enum
from typing import Any, Callable, List, Optional

logger = logging.getLogger("hive.pubsub")


class HiveEvent(str, Enum):
    TELEMETRY_UPDATED = "TELEMETRY_UPDATED"
    STATUS_CHANGED    = "STATUS_CHANGED"
    TRANSFER_PROGRESS = "TRANSFER_PROGRESS"
    DISCOVERY_GROUPS_UPDATED = "DISCOVERY_GROUPS_UPDATED"
    NETWORK_STATE_CHANGED = "NETWORK_STATE_CHANGED"
    SWARM_ROLE_CHANGED = "SWARM_ROLE_CHANGED"
    SESSION_PEERS_UPDATED = "SESSION_PEERS_UPDATED"
    TRANSFER_TARGETS_UPDATED = "TRANSFER_TARGETS_UPDATED"
    DATA_PLANE_STATE_CHANGED = "DATA_PLANE_STATE_CHANGED"
    TRANSFER_ERROR = "TRANSFER_ERROR"
    SEND_COMPLETE = "SEND_COMPLETE"
    RECEIVE_COMPLETE = "RECEIVE_COMPLETE"
    SHOW_SCREEN = "SHOW_SCREEN"
    PEER_DISCOVERED   = "PEER_DISCOVERED"
    PEER_LEFT         = "PEER_LEFT"
    PEER_STATE_CHANGED = "PEER_STATE_CHANGED"
    HEARTBEAT_METRICS = "HEARTBEAT_METRICS"
    HOST_ELECTED      = "HOST_ELECTED"
    CHAT_RECEIVED     = "CHAT_RECEIVED"
    LOG_MESSAGE       = "LOG_MESSAGE"
    INCOMING_TRANSFER = "INCOMING_TRANSFER"


class _Ref:
    __slots__ = ("_ref", "_is_weak")

    def __init__(self, handler: Callable) -> None:
        try:
            self._ref = weakref.WeakMethod(handler)
            self._is_weak = True
        except TypeError:
            self._ref = handler
            self._is_weak = False

    def __call__(self):
        if self._is_weak:
            return self._ref()
        return self._ref


class HiveEventBus:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        ui=None,
    ) -> None:
        self._loop = loop
        self.ui = ui
        self._subscribers: dict = {}

    def subscribe(self, event: HiveEvent, handler: Callable) -> None:
        if not isinstance(event, HiveEvent):
            raise TypeError(
                f"bus.subscribe() requires a HiveEvent member, got {event!r}. "
                "Did you pass a raw string?"
            )
        refs = self._subscribers.setdefault(event, [])
        refs.append(_Ref(handler))

    def publish(
        self,
        event: HiveEvent,
        data: Any = None,
        trace_id: str = "",
        no_log: bool = False,
    ) -> None:
        if not isinstance(event, HiveEvent):
            raise TypeError(
                f"bus.publish() requires a HiveEvent member, got {event!r}."
            )

        if not no_log:
            logger.debug(
                "[BUS][%s][%.4f] %s",
                trace_id or "GLOBAL",
                time.perf_counter(),
                event.name,
            )

        refs = self._subscribers.get(event)
        if not refs:
            return

        live_refs: List[_Ref] = []
        live_handlers: List[Callable] = []
        for ref in refs:
            handler = ref()
            if handler is not None:
                live_refs.append(ref)
                live_handlers.append(handler)
        self._subscribers[event] = live_refs

        for handler in live_handlers:
            self._dispatch(handler, event, data)

    def _dispatch(self, handler: Callable, event: HiveEvent, data: Any) -> None:
        if asyncio.iscoroutinefunction(handler):
            self._dispatch_async(handler, event, data)
        else:
            self._dispatch_sync(handler, event, data)

    def _dispatch_async(self, handler: Callable, event: HiveEvent, data: Any) -> None:
        def _schedule():
            self._loop.create_task(handler(event, data))

        self._loop.call_soon_threadsafe(_schedule)

    def _dispatch_sync(self, handler: Callable, event: HiveEvent, data: Any) -> None:
        if self.ui is not None:
            self.ui.after(0, lambda h=handler, e=event, d=data: h(e, d))
        else:
            handler(event, data)

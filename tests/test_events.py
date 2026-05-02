"""
tests/test_events.py — HiveEventBus unit tests (Phase 0 gate)

Five tests that prove the bus is solid before any application code
is touched.  These tests must pass and continue to pass unchanged
through all subsequent migration phases.
"""

import asyncio
import gc
import threading
import time

import pytest

from app.core.events import HiveEvent, HiveEventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop():
    """Return a fresh event loop suitable for use in tests."""
    return asyncio.new_event_loop()


class _FakeUI:
    """Minimal stand-in for Tkinter root: captures after() calls."""
    def __init__(self):
        self.calls = []

    def after(self, delay, fn):
        # Execute immediately so tests don't need a real mainloop.
        self.calls.append(fn)
        fn()


# ---------------------------------------------------------------------------
# R2 — Enum guard
# ---------------------------------------------------------------------------

class TestEnumGuard:
    def test_subscribe_rejects_raw_string(self):
        loop = _make_loop()
        bus = HiveEventBus(loop)
        with pytest.raises(TypeError, match="HiveEvent member"):
            bus.subscribe("PEER_JONED", lambda e, d: None)

    def test_publish_rejects_raw_string(self):
        loop = _make_loop()
        bus = HiveEventBus(loop)
        with pytest.raises(TypeError, match="HiveEvent member"):
            bus.publish("TELEMETRY_UPDATED", {})

    def test_subscribe_accepts_enum_member(self):
        loop = _make_loop()
        bus = HiveEventBus(loop)
        # Should not raise
        bus.subscribe(HiveEvent.TELEMETRY_UPDATED, lambda e, d: None)


# ---------------------------------------------------------------------------
# R1 / R7 — Thread-boundary: ui.after() is called for sync handlers
# ---------------------------------------------------------------------------

class TestUIThreadBoundary:
    def test_ui_after_called_for_sync_handler(self):
        loop = _make_loop()
        ui = _FakeUI()
        bus = HiveEventBus(loop, ui=ui)

        received = []
        bus.subscribe(HiveEvent.STATUS_CHANGED, lambda e, d: received.append(d))

        bus.publish(HiveEvent.STATUS_CHANGED, "CONNECTED")

        # _FakeUI.after() executes the lambda immediately, so we
        # check that the handler fired AND that after() was called.
        assert "CONNECTED" in received
        assert len(ui.calls) == 1

    def test_headless_sync_handler_called_inline(self):
        """With ui=None the handler must still be called (R7)."""
        loop = _make_loop()
        bus = HiveEventBus(loop, ui=None)

        received = []
        bus.subscribe(HiveEvent.STATUS_CHANGED, lambda e, d: received.append(d))
        bus.publish(HiveEvent.STATUS_CHANGED, "HEADLESS")

        assert received == ["HEADLESS"]


# ---------------------------------------------------------------------------
# R6 — Async handler fires via loop.create_task
# ---------------------------------------------------------------------------

class TestAsyncHandler:
    def test_async_handler_receives_event(self):
        loop = _make_loop()
        bus = HiveEventBus(loop, ui=None)

        results = []

        async def async_handler(event, data):
            results.append((event, data))

        bus.subscribe(HiveEvent.TELEMETRY_UPDATED, async_handler)

        # Run the loop briefly so the scheduled task executes.
        def _publish_and_run():
            bus.publish(HiveEvent.TELEMETRY_UPDATED, {"score": 99})
            loop.run_until_complete(asyncio.sleep(0.05))

        t = threading.Thread(target=lambda: loop.run_forever())
        loop.call_soon_threadsafe(lambda: None)  # warm up
        t.start()

        bus.publish(HiveEvent.TELEMETRY_UPDATED, {"score": 99})
        time.sleep(0.1)  # allow the task to complete
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=2)

        assert len(results) == 1
        assert results[0] == (HiveEvent.TELEMETRY_UPDATED, {"score": 99})


# ---------------------------------------------------------------------------
# R3 — Weakref: dead handlers are pruned, no crash
# ---------------------------------------------------------------------------

class TestWeakrefPruning:
    def test_dead_handler_is_pruned_and_no_crash(self):
        loop = _make_loop()
        bus = HiveEventBus(loop, ui=None)

        class _Subscriber:
            def __init__(self):
                self.called = False
            def handle(self, event, data):
                self.called = True

        sub = _Subscriber()
        bus.subscribe(HiveEvent.PEER_DISCOVERED, sub.handle)

        # Delete the subscriber and force GC.
        del sub
        gc.collect()

        # Must not raise, and the dead ref must be pruned.
        bus.publish(HiveEvent.PEER_DISCOVERED, "some-uuid")
        assert bus._subscribers[HiveEvent.PEER_DISCOVERED] == []

    def test_live_handler_still_fires_alongside_dead_one(self):
        loop = _make_loop()
        bus = HiveEventBus(loop, ui=None)

        class _Dying:
            def handle(self, event, data): pass

        received = []
        live_fn = lambda e, d: received.append(d)  # noqa: E731

        dying = _Dying()
        bus.subscribe(HiveEvent.PEER_DISCOVERED, dying.handle)
        bus.subscribe(HiveEvent.PEER_DISCOVERED, live_fn)

        del dying
        gc.collect()

        bus.publish(HiveEvent.PEER_DISCOVERED, "peer-abc")
        assert received == ["peer-abc"]

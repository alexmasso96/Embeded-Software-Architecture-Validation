"""
SSE event bus (plan §3.1): a single stream carrying job progress, db-changed,
and lock events to the UI.

Publishers are usually worker threads (job callbacks, the lock heartbeat), so
``publish`` is thread-safe: it hops onto the event loop with
``call_soon_threadsafe`` and fans the event out to every subscribed asyncio
queue. The SSE endpoint drains one queue per connected client.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup so worker-thread publishers can reach the loop."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event_type: str, data: Any) -> None:
        """Fan ``{"type": event_type, "data": data}`` out to all subscribers.

        Safe to call from any thread. A no-op if the loop isn't bound yet
        (e.g. events emitted before startup) — those are simply dropped.
        """
        event = {"type": event_type, "data": data}
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._fanout, event)
        except RuntimeError:
            # Loop already closed (shutting down) — drop the event.
            pass

    def _fanout(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - unbounded queues
                logger.warning("SSE subscriber queue full; dropping event %s", event["type"])

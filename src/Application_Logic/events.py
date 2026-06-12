"""
Dependency-free event emitter — the Phase 0 replacement for Qt signals.

Logic classes own an ``Emitter`` instance (conventionally ``self.events``) and
publish with ``self.events.emit("progress", 42)`` where they previously did
``self.progress.emit(42)``. Subscribers register with ``events.on("progress", fn)``.

Delivery is synchronous and in-order on the emitting thread. Cross-thread
marshalling (e.g. back onto the Qt GUI thread) is the subscriber's job — during
the transition the PyQt side bridges via ``src/UI/qt_bridge.py``; after Phase 1
the FastAPI worker forwards events onto the SSE bus.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


class Emitter:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable]] = {}
        # Optional catch-all hook: called as on_any(event, args, kwargs) for
        # every emit. Used by the Qt bridge to relay all events thread-safely.
        self.on_any: Optional[Callable[[str, tuple, dict], None]] = None

    def on(self, event: str, fn: Callable) -> Callable:
        """Subscribe ``fn`` to ``event``. Returns ``fn`` unchanged for chaining."""
        self._subs.setdefault(event, []).append(fn)
        return fn

    def off(self, event: str, fn: Callable) -> None:
        """Unsubscribe ``fn`` from ``event``. Missing subscriptions are ignored."""
        try:
            self._subs.get(event, []).remove(fn)
        except ValueError:
            pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for fn in list(self._subs.get(event, [])):
            fn(*args, **kwargs)
        if self.on_any is not None:
            self.on_any(event, args, kwargs)

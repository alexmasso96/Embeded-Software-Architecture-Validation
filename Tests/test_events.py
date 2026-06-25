"""
Unit tests for Application_Logic.events.Emitter — the Qt-signal replacement
introduced in Phase 0 of the pywebview migration.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from Application_Logic.events import Emitter


def test_on_and_emit_positional_and_keyword_args():
    em = Emitter()
    received = []
    em.on("progress", lambda *a, **kw: received.append((a, kw)))
    em.emit("progress", 42, message="halfway")
    assert received == [((42,), {"message": "halfway"})]


def test_emit_with_no_subscribers_is_a_noop():
    Emitter().emit("nobody-listening", 1, 2)


def test_multiple_subscribers_called_in_registration_order():
    em = Emitter()
    order = []
    em.on("ev", lambda: order.append("first"))
    em.on("ev", lambda: order.append("second"))
    em.emit("ev")
    assert order == ["first", "second"]


def test_off_unsubscribes_and_tolerates_unknown():
    em = Emitter()
    hits = []
    fn = lambda: hits.append(1)
    em.on("ev", fn)
    em.off("ev", fn)
    em.emit("ev")
    assert hits == []
    em.off("ev", fn)            # already removed — no error
    em.off("never-registered", fn)


def test_on_returns_fn_unchanged():
    em = Emitter()
    hits = []

    def handler(x):
        hits.append(x)

    assert em.on("ev", handler) is handler
    em.emit("ev", 7)
    assert hits == [7]


def test_on_any_receives_every_event():
    em = Emitter()
    seen = []
    em.on_any = lambda ev, args, kw: seen.append((ev, args, kw))
    em.emit("a", 1)
    em.emit("b", flag=True)
    assert seen == [("a", (1,), {}), ("b", (), {"flag": True})]


def test_subscriber_added_during_emit_does_not_fire_in_same_emit():
    em = Emitter()
    hits = []
    em.on("ev", lambda: em.on("ev", lambda: hits.append("late")))
    em.emit("ev")
    assert hits == []
    em.emit("ev")
    assert hits == ["late"]

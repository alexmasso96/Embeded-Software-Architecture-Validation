"""
Job handlers (plan §3.1). Each adapts a pure ``Logic_*`` job function to the
``(params, progress, cancel_event) -> result`` contract and is registered with
the JobManager under its kind.

The pure jobs already take a ``progress_cb`` and (where relevant) open their own
SQLite connection on the worker thread — that own-connection rule is what keeps
a build crash-free while the main connection is busy (see build_code_map_job /
run_release_diff). Handlers therefore stay thin.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from Application_Logic.Logic_Change_Log_Tab import run_release_diff
from Application_Logic.Logic_Code_Map_Tab import build_code_map_job

from .jobs import JobManager
from .state import AppState, ProjectError


def register_handlers(jobs: JobManager, state: AppState) -> None:
    jobs.register("_demo", _demo_handler)
    jobs.register("release_diff", _make_release_diff(state))
    jobs.register("build_code_map", _make_build_code_map(state))


# ----------------------------------------------------------------------
# _demo — a dependency-free job for exercising the lifecycle/SSE/cancel path
# in tests without ELF or project fixtures.
# ----------------------------------------------------------------------
def _demo_handler(params: dict, progress: Callable[..., None],
                  cancel: threading.Event):
    steps = int(params.get("steps", 3))
    delay = float(params.get("delay", 0.0))
    done = 0
    for i in range(steps):
        if cancel.is_set():
            break
        done = i + 1
        progress(f"step {done}/{steps}", percent=100.0 * done / steps)
        if delay:
            time.sleep(delay)
    return {"steps_completed": done, "echo": params.get("echo")}


# ----------------------------------------------------------------------
def _make_release_diff(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        db = state.require_open()
        cur = params.get("current_release_id")
        prev = params.get("previous_release_id")
        if cur is None or prev is None:
            raise ProjectError("current_release_id and previous_release_id are required.")
        progress("Computing release diff…")
        diff_hash, diffs = run_release_diff(db.db_path, cur, prev)
        return {"diff_hash": diff_hash, "file_count": len(diffs)}
    return handler


# ----------------------------------------------------------------------
def _make_build_code_map(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        db = state.require_open()
        model_id = params.get("model_id")
        if model_id is None:
            raise ProjectError("model_id is required.")
        code_map = build_code_map_job(
            db.db_path,
            params.get("elf_hash"),
            params.get("elf_path"),
            params.get("source_dir"),
            model_id,
            params.get("release_id"),
            progress_cb=lambda msg: progress(msg),
        )
        return {"functions": len(code_map.get("functions", {}))}
    return handler

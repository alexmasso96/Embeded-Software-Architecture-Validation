"""Shared FastAPI dependencies — pull the singletons off app.state."""
from __future__ import annotations

from fastapi import Request

from .events import EventBus
from .jobs import JobManager
from .state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.appstate


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus

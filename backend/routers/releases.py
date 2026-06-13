"""
Releases router (plan §3.2): list / create / activate / rename / delete.

Releases are real software releases (newest first; create inserts at index 0).
Baselines are frozen snapshots — they show up in the list with ``is_baseline``
but are filtered out of the source/release pickers (``selectable``). Baseline
*creation* needs the layout + active-model snapshot and lands in a follow-up
(it maps to plan §3's ``create_baseline`` job).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_bus, get_state
from ..events import EventBus
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/releases", tags=["releases"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


class CreateReleaseBody(BaseModel):
    name: str
    description: str = ""
    copy_from_active: bool = False
    baseline_previous: bool = False


class RenameReleaseBody(BaseModel):
    name: str


def _release_view(rm, db, r, active_id) -> dict:
    has_source = db.has_release_source(r.id) if r.id is not None else False
    return {
        "id": r.id,
        "name": r.name,
        "is_baseline": r.is_baseline,
        "is_deleted": r.is_deleted,
        "parent_release_name": r.parent_release_name,
        "description": r.description,
        "timestamp": r.timestamp,
        "elf_hash": r.elf_hash,
        "has_source": has_source,
        "is_active": r.id == active_id,
        # 'selectable' = a real release offered in pickers (#2E).
        "selectable": (not r.is_baseline and not r.is_deleted),
    }


@router.get("")
def list_releases(include_deleted: bool = False,
                  state: AppState = Depends(get_state)) -> dict:
    def go():
        rm = state.require_releases()
        db = state.require_open()
        active = rm.get_active_release()
        active_id = active.id if active else None
        out = [_release_view(rm, db, r, active_id)
               for r in rm.releases if include_deleted or not r.is_deleted]
        return {"releases": out, "active_release_id": active_id}
    return _guard(go)


@router.post("")
def create_release(body: CreateReleaseBody, state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        try:
            r = rm.create_release(
                body.name, description=body.description,
                copy_from_active=body.copy_from_active,
                baseline_previous=body.baseline_previous,
            )
        except ValueError as e:
            raise ProjectError(str(e)) from e
        bus.publish("db-changed", {"reason": "release-created", "release_id": r.id})
        return {"id": r.id, "name": r.name}
    return _guard(go)


@router.post("/{release_id}/activate")
def activate_release(release_id: int, state: AppState = Depends(get_state),
                     bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        rm.set_active_release(idx)
        bus.publish("db-changed", {"reason": "release-activated", "release_id": release_id})
        return state.status()
    return _guard(go)


@router.patch("/{release_id}")
def rename_release(release_id: int, body: RenameReleaseBody,
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        ok, msg = rm.rename_release(idx, body.name)
        if not ok:
            raise ProjectError(msg)
        bus.publish("db-changed", {"reason": "release-renamed", "release_id": release_id})
        return {"id": release_id, "name": body.name}
    return _guard(go)


@router.delete("/{release_id}")
def delete_release(release_id: int, comment: str = "",
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        ok, msg = rm.delete_release(idx, deletion_comment=comment)
        if not ok:
            raise ProjectError(msg)
        bus.publish("db-changed", {"reason": "release-deleted", "release_id": release_id})
        return {"id": release_id, "result": msg}
    return _guard(go)

"""
Project lifecycle router (plan §3.2): new / open / save / close / status.

Paths are real filesystem paths (the worker needs them for .arch/ELF/source
folders on network shares); the desktop shell supplies them via native dialogs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError, MODE_EXCLUSIVE, MODE_VIEW

router = APIRouter(prefix="/api/project", tags=["project"],
                   dependencies=[Depends(require_token)])


class NewProjectBody(BaseModel):
    path: str


class OpenProjectBody(BaseModel):
    path: str
    mode: str = MODE_EXCLUSIVE     # "exclusive" | "view"


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/new")
def new_project(body: NewProjectBody, state: AppState = Depends(get_state)) -> dict:
    return _guard(lambda: state.new_project(body.path))


@router.post("/open")
def open_project(body: OpenProjectBody, state: AppState = Depends(get_state)) -> dict:
    if body.mode not in (MODE_EXCLUSIVE, MODE_VIEW):
        raise HTTPException(status_code=422, detail=f"Unknown mode: {body.mode}")
    return _guard(lambda: state.open_project(body.path, body.mode))


@router.post("/save")
def save_project(state: AppState = Depends(get_state)) -> dict:
    return _guard(state.save_project)


@router.post("/close")
def close_project(state: AppState = Depends(get_state)) -> dict:
    return _guard(state.close_project)


@router.get("/status")
def status(state: AppState = Depends(get_state)) -> dict:
    return state.status()

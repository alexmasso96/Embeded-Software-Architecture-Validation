"""
Filesystem browse router (Phase 2 dev support).

Browsers can't return real absolute paths, and the native file dialogs only
arrive with the pywebview shell (Phase 3). To let the React launcher offer a
real folder/.arch picker during browser development, the worker exposes a
read-only directory listing. It is token-protected and local-only, same as
every other route.

Listing surfaces directories and ``.arch`` files only (the things the launcher
navigates and selects); dotfiles are hidden.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..security import require_token

router = APIRouter(prefix="/api/fs", tags=["fs"],
                   dependencies=[Depends(require_token)])


def _entry(p: Path) -> dict:
    try:
        is_dir = p.is_dir()
    except OSError:
        is_dir = False
    return {
        "name": p.name,
        "path": str(p),
        "is_dir": is_dir,
        "is_arch": (not is_dir) and p.suffix.lower() == ".arch",
    }


@router.get("/home")
def home() -> dict:
    """The default starting directory for the picker."""
    return {"home": str(Path.home())}


@router.get("/list")
def list_dir(path: str | None = Query(None)) -> dict:
    """List the directories and ``.arch`` files under ``path`` (default: home)."""
    base = Path(path).expanduser() if path else Path.home()
    try:
        base = base.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}") from e
    if not base.exists():
        raise HTTPException(status_code=404, detail=f"No such path: {base}")
    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {base}")

    entries: list[dict] = []
    try:
        children = sorted(
            base.iterdir(),
            key=lambda c: (not _is_dir_safe(c), c.name.lower()),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"Permission denied: {base}") from e

    for child in children:
        if child.name.startswith("."):
            continue
        e = _entry(child)
        if e["is_dir"] or e["is_arch"]:
            entries.append(e)

    parent = str(base.parent)
    return {
        "path": str(base),
        "parent": parent if parent != str(base) else None,
        "sep": os.sep,
        "entries": entries,
    }


def _is_dir_safe(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


class MkdirBody(BaseModel):
    parent: str
    name: str


@router.post("/mkdir")
def mkdir(body: MkdirBody) -> dict:
    """Create a single new directory ``name`` inside ``parent`` (for the picker's
    'New Folder' affordance). Rejects path separators and existing targets."""
    name = body.name.strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid folder name.")
    try:
        parent = Path(body.parent).expanduser().resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parent: {e}") from e
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {parent}")
    target = parent / name
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Already exists: {target}")
    try:
        target.mkdir()
    except OSError as e:
        raise HTTPException(status_code=403, detail=f"Could not create folder: {e}") from e
    return _entry(target)

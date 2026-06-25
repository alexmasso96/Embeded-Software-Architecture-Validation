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
import string
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..security import require_token

router = APIRouter(prefix="/api/fs", tags=["fs"],
                   dependencies=[Depends(require_token)])


def _list_drives() -> list[dict]:
    """Logical drive/volume roots for the picker's quick-switch shortcuts.

      * Windows — every present logical drive letter (``C:\\``, ``D:\\``…).
      * macOS   — root ``/`` plus each mounted volume under ``/Volumes``.
      * Linux   — root ``/`` plus mounts under ``/media`` and ``/mnt``.
    Each entry is ``{"name", "path"}``; unreadable roots are skipped.
    """
    drives: list[dict] = []
    if os.name == "nt":
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        except Exception:  # noqa: BLE001 — fall back to brute-force existence check
            bitmask = 0
        for i, letter in enumerate(string.ascii_uppercase):
            present = (bitmask >> i) & 1 if bitmask else os.path.exists(f"{letter}:\\")
            if present:
                root = f"{letter}:\\"
                drives.append({"name": root, "path": root})
        return drives

    # POSIX: always offer the filesystem root, then mounted media/volumes.
    drives.append({"name": "/", "path": "/"})
    mount_parents = ["/Volumes"] if sys.platform == "darwin" else ["/media", "/mnt"]
    for parent in mount_parents:
        p = Path(parent)
        if not p.is_dir():
            continue
        try:
            children = sorted(p.iterdir(), key=lambda c: c.name.lower())
        except OSError:
            continue
        for child in children:
            if child.name.startswith("."):
                continue
            if _is_dir_safe(child):
                drives.append({"name": child.name, "path": str(child)})
    return drives


@router.get("/drives")
def drives() -> dict:
    """Logical drives (Windows) or volume/mount roots (macOS/Linux) as picker
    shortcuts. Always returns at least one entry (the root) on POSIX."""
    return {"drives": _list_drives()}


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
def list_dir(path: str | None = Query(None),
             exts: str = Query(".arch")) -> dict:
    """List the directories and selectable files under ``path`` (default: home).

    ``exts`` is a comma-separated allow-list of file extensions to surface
    (default ``.arch``; the Import picker passes ``.elf,.json``). Directories are
    always listed; dotfiles are hidden.
    """
    allowed = {e.strip().lower() for e in exts.split(",") if e.strip()}
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
        if e["is_dir"] or child.suffix.lower() in allowed:
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

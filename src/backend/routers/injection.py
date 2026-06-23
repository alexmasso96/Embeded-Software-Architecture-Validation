"""
Source-Level Test Code Injection router.

Owns the test-project lifecycle (create/list/delete), helper-file import, the
injection hooks, fuzzy anchor resolution/shifting, source export, and the build
runner. Reads/writes go through ``AppState`` (the open .arch); the production
source it injects into comes from the active release's DB-stored source (#2E).

The build runner spawns a compiler in a subprocess on a worker thread and streams
its output line-by-line over the shared ``build`` SSE event so the frontend
console can scroll logs live. It runs independently of export.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_bus, get_state
from ..events import EventBus
from ..security import require_token
from ..state import AppState, ProjectError

from Application_Logic import Logic_Code_Injection as injection
from Application_Logic.Logic_Source_Store import (
    FilesystemSourceProvider, SourceFile, SOURCE_EXTENSIONS,
    release_source_provider,
)

router = APIRouter(prefix="/api/injection", tags=["injection"],
                   dependencies=[Depends(require_token)])

# Terminal kinds we know how to launch (read from project settings).
TERMINALS = {"cmd", "powershell", "bash", "wsl"}

# Active build subprocesses, keyed by build_id (so they can be cancelled).
_builds: dict[str, subprocess.Popen] = {}
_builds_lock = threading.Lock()


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ----------------------------------------------------------------------
# Production-source helpers (active release's DB-stored source)
# ----------------------------------------------------------------------
def _production_provider(state: AppState):
    """A source provider for the active release's production source, or raise."""
    db = state.require_open()
    rm = state.require_releases()
    active = rm.get_active_release()
    rid = active.id if active else None
    provider = release_source_provider(db, rid)
    if provider is None:
        raise ProjectError(
            "No source imported for the active release. Import release source "
            "before injecting test code.")
    return provider


def _read_production_lines(state: AppState, rel_path: str) -> list[str]:
    text = _production_provider(state).read_file(rel_path)
    if text is None:
        raise ProjectError(f"No such source file in the active release: {rel_path}")
    return text.splitlines()


class _SingleFileProvider:
    """Minimal SourceProvider over one in-memory file (for a cheap one-file
    CodeIndex when we only need a single function's boundaries)."""

    def __init__(self, rel_path: str, text: str):
        self.rel_path = rel_path
        self.text = text
        self.ext = os.path.splitext(rel_path)[1].lower()

    def list_files(self, exts=None):
        return [SourceFile(self.rel_path, len(self.text), self.ext)]

    def read_file(self, rel_path: str):
        return self.text if rel_path == self.rel_path else None

    def iter_text(self, exts=None):
        yield self.rel_path, self.text

    def change_key(self, sf):
        return (len(self.text),)


def _function_bounds(rel_path: str, text: str, function_name: str):
    """``(line_start, line_end)`` for ``function_name`` via a one-file CodeIndex."""
    if not function_name:
        return None
    from Application_Logic.Logic_Code_Index import build_index
    try:
        idx = build_index(_SingleFileProvider(rel_path, text))
    except Exception:  # noqa: BLE001 — indexing best-effort; fall back to no bounds
        return None
    return injection.function_bounds(idx, function_name)


def _require_test_project(state: AppState, test_project_id: int):
    db = state.require_open()
    for p in db.list_test_projects():
        if p["id"] == test_project_id:
            return db
    raise ProjectError(f"No such test project: {test_project_id}")


# ----------------------------------------------------------------------
# Test projects
# ----------------------------------------------------------------------
@router.get("/projects")
def list_projects(state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        return {"projects": db.list_test_projects()}
    return _guard(go)


class CreateProjectBody(BaseModel):
    name: str


@router.post("/projects")
def create_project(body: CreateProjectBody, state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        name = body.name.strip()
        if not name:
            raise ProjectError("Test project name cannot be empty.")
        pid = db.create_test_project(name)
        bus.publish("db-changed", {"reason": "test-project-created", "id": pid})
        return {"id": pid, "name": name}
    return _guard(go)


class RenameProjectBody(BaseModel):
    name: str


@router.patch("/projects/{test_project_id}")
def rename_project(test_project_id: int, body: RenameProjectBody,
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        _require_test_project(state, test_project_id)
        name = body.name.strip()
        if not name:
            raise ProjectError("Test project name cannot be empty.")
        db.rename_test_project(test_project_id, name)
        bus.publish("db-changed", {"reason": "test-project-renamed",
                                   "id": test_project_id})
        return {"id": test_project_id, "name": name}
    return _guard(go)


@router.delete("/projects/{test_project_id}")
def delete_project(test_project_id: int, state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        db.delete_test_project(test_project_id)
        bus.publish("db-changed", {"reason": "test-project-deleted",
                                   "id": test_project_id})
        return {"id": test_project_id, "deleted": True}
    return _guard(go)


# ----------------------------------------------------------------------
# Helper-file import
# ----------------------------------------------------------------------
class ImportFile(BaseModel):
    rel_path: str
    content: str


class ImportBody(BaseModel):
    # Either walk a folder for .c/.h files, or pass explicit file contents.
    folder: Optional[str] = None
    files: Optional[list[ImportFile]] = None


@router.post("/projects/{test_project_id}/import")
def import_files(test_project_id: int, body: ImportBody,
                 state: AppState = Depends(get_state),
                 bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        _require_test_project(state, test_project_id)
        pairs: list[tuple[str, str]] = []
        if body.folder:
            provider = FilesystemSourceProvider(body.folder)
            # Helper files are C/C++ sources only.
            for rel, text in provider.iter_text(SOURCE_EXTENSIONS):
                pairs.append((rel, text))
        if body.files:
            for f in body.files:
                ext = os.path.splitext(f.rel_path)[1].lower()
                if ext in SOURCE_EXTENSIONS:
                    pairs.append((f.rel_path, f.content))
        if not pairs:
            raise ProjectError("No .c/.h helper files found to import.")
        count = db.import_test_project_files(test_project_id, pairs)
        bus.publish("db-changed", {"reason": "test-files-imported",
                                   "id": test_project_id, "count": count})
        return {"id": test_project_id, "imported": count}
    return _guard(go)


@router.get("/projects/{test_project_id}/files")
def list_files(test_project_id: int, state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        return {"files": db.list_test_project_files(test_project_id)}
    return _guard(go)


@router.get("/projects/{test_project_id}/files/content")
def read_file(test_project_id: int, rel_path: str = Query(...),
              state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        text = db.read_test_project_file(test_project_id, rel_path)
        if text is None:
            raise ProjectError(f"No such helper file: {rel_path}")
        return {"rel_path": rel_path, "content": text}
    return _guard(go)


@router.delete("/projects/{test_project_id}/files")
def delete_file(test_project_id: int, rel_path: str = Query(...),
                state: AppState = Depends(get_state),
                bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        db.delete_test_project_file(test_project_id, rel_path)
        bus.publish("db-changed", {"reason": "test-file-deleted",
                                   "id": test_project_id})
        return {"id": test_project_id, "rel_path": rel_path, "deleted": True}
    return _guard(go)


# ----------------------------------------------------------------------
# Production source listing (the tree the user injects into)
# ----------------------------------------------------------------------
@router.get("/source/files")
def source_files(state: AppState = Depends(get_state)) -> dict:
    """List the active release's production source files (for the file tree)."""
    def go():
        provider = _production_provider(state)
        return {"files": [{"rel_path": sf.rel_path, "size": sf.size, "ext": sf.ext}
                          for sf in provider.list_files()]}
    return _guard(go)


@router.get("/source/content")
def source_content(rel_path: str = Query(...),
                   state: AppState = Depends(get_state)) -> dict:
    def go():
        text = _production_provider(state).read_file(rel_path)
        if text is None:
            raise ProjectError(f"No such source file: {rel_path}")
        return {"rel_path": rel_path, "content": text}
    return _guard(go)


# ----------------------------------------------------------------------
# Injection hooks
# ----------------------------------------------------------------------
class InjectionBody(BaseModel):
    injection_id: Optional[int] = None   # present → update, absent → add
    src_file_path: str
    function_name: str = ""
    line_above_code: str = ""
    line_below_code: str = ""
    injected_code: str = ""
    offset_lines: int = 0


@router.get("/projects/{test_project_id}/injections")
def list_injections(test_project_id: int, src_file_path: Optional[str] = None,
                    state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        rows = db.list_injections(test_project_id, src_file_path)
        # Annotate each hook with its current resolution against live source.
        out = []
        for r in rows:
            try:
                lines = _read_production_lines(state, r["src_file_path"])
                res = injection.resolve_injection(
                    lines, r["line_above_code"], r["line_below_code"])
            except ProjectError:
                res = {"index": None, "confidence": 0, "anchor": "none"}
            out.append({**r, "resolved_index": res["index"],
                        "confidence": res["confidence"], "anchor": res["anchor"]})
        return {"injections": out}
    return _guard(go)


@router.post("/projects/{test_project_id}/injections")
def upsert_injection(test_project_id: int, body: InjectionBody,
                     state: AppState = Depends(get_state),
                     bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        _require_test_project(state, test_project_id)
        if body.injection_id is not None:
            db.update_injection(
                body.injection_id,
                src_file_path=body.src_file_path,
                function_name=body.function_name,
                line_above_code=body.line_above_code,
                line_below_code=body.line_below_code,
                injected_code=body.injected_code,
                offset_lines=body.offset_lines)
            iid = body.injection_id
        else:
            iid = db.add_injection(
                test_project_id, body.src_file_path, body.function_name,
                body.line_above_code, body.line_below_code,
                body.injected_code, body.offset_lines)
        bus.publish("db-changed", {"reason": "injection-saved",
                                   "id": test_project_id, "injection_id": iid})
        return {"injection_id": iid}
    return _guard(go)


@router.delete("/injections/{injection_id}")
def remove_injection(injection_id: int, state: AppState = Depends(get_state),
                     bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        db.remove_injection(injection_id)
        bus.publish("db-changed", {"reason": "injection-removed",
                                   "injection_id": injection_id})
        return {"injection_id": injection_id, "deleted": True}
    return _guard(go)


class ResolveBody(BaseModel):
    src_file_path: str
    line_above_code: str = ""
    line_below_code: str = ""


@router.post("/resolve")
def resolve(body: ResolveBody, state: AppState = Depends(get_state)) -> dict:
    """Resolve a candidate splice point against the live source (for the UI's
    confidence badge / conflict placeholder)."""
    def go():
        lines = _read_production_lines(state, body.src_file_path)
        return injection.resolve_injection(
            lines, body.line_above_code, body.line_below_code)
    return _guard(go)


class ShiftBody(BaseModel):
    direction: str   # "up" | "down"


@router.post("/injections/{injection_id}/shift")
def shift(injection_id: int, body: ShiftBody,
          state: AppState = Depends(get_state),
          bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        inj = db.get_injection(injection_id)
        if inj is None:
            raise ProjectError(f"No such injection: {injection_id}")
        text = _production_provider(state).read_file(inj["src_file_path"])
        if text is None:
            raise ProjectError(f"No such source file: {inj['src_file_path']}")
        lines = text.splitlines()
        bounds = _function_bounds(inj["src_file_path"], text, inj["function_name"])
        result = injection.shift_injection(
            lines, injection_id, body.direction, db, func_bounds=bounds)
        if not result.get("ok"):
            raise ProjectError(result.get("reason", "Shift refused."))
        bus.publish("db-changed", {"reason": "injection-shifted",
                                   "injection_id": injection_id})
        return result
    return _guard(go)


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------
class ExportBody(BaseModel):
    mode: str = "modified"        # "modified" | "reconstruct"
    out_dir: str
    overwrite: bool = False       # allow writing into a non-empty directory


def _write_file(out_dir: str, rel_path: str, text: str) -> str:
    target = os.path.join(out_dir, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(target) or out_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return target


@router.post("/projects/{test_project_id}/export")
def export(test_project_id: int, body: ExportBody,
           state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        _require_test_project(state, test_project_id)
        if body.mode not in ("modified", "reconstruct"):
            raise ProjectError(f"Unknown export mode: {body.mode}")
        out_dir = body.out_dir
        if not out_dir:
            raise ProjectError("An output directory is required.")
        if os.path.isdir(out_dir) and os.listdir(out_dir) and not body.overwrite:
            raise ProjectError(
                "Output directory is not empty. Enable overwrite to proceed.")
        os.makedirs(out_dir, exist_ok=True)

        provider = _production_provider(state)
        all_injections = db.list_injections(test_project_id)
        by_file: dict[str, list] = {}
        for inj in all_injections:
            by_file.setdefault(inj["src_file_path"], []).append(inj)

        written: list[str] = []
        conflicts: list[dict] = []

        def emit_production(rel_path: str):
            text = provider.read_file(rel_path)
            if text is None:
                return
            hooks = by_file.get(rel_path)
            if hooks:
                text, results = injection.apply_injections(text, hooks)
                conflicts.extend(
                    {"src_file_path": rel_path, "injection_id": r["injection_id"]}
                    for r in results if not r["applied"])
            written.append(_write_file(out_dir, rel_path, text))

        if body.mode == "modified":
            for rel_path in by_file:
                emit_production(rel_path)
        else:  # reconstruct: every production file
            for sf in provider.list_files():
                emit_production(sf.rel_path)

        # Test helper files are always exported (under their own rel paths).
        for f in db.list_test_project_files(test_project_id):
            text = db.read_test_project_file(test_project_id, f["rel_path"])
            if text is not None:
                written.append(_write_file(out_dir, f["rel_path"], text))

        return {"out_dir": out_dir, "count": len(written),
                "written": written, "conflicts": conflicts}
    return _guard(go)


# ----------------------------------------------------------------------
# Build settings + runner
# ----------------------------------------------------------------------
@router.get("/settings")
def get_settings(state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        return {
            "terminal": db.get_meta("inject_terminal", "bash"),
            "wsl_distro": db.get_meta("inject_wsl_distro", ""),
            "build_command": db.get_meta("inject_build_command", ""),
            "build_cwd": db.get_meta("inject_build_cwd", ""),
            "make_script": db.get_meta("inject_make_script", ""),
            "source_path": db.get_meta("inject_source_path", ""),
        }
    return _guard(go)


class SettingsBody(BaseModel):
    terminal: Optional[str] = None
    wsl_distro: Optional[str] = None
    build_command: Optional[str] = None
    build_cwd: Optional[str] = None
    make_script: Optional[str] = None
    source_path: Optional[str] = None


@router.post("/settings")
def set_settings(body: SettingsBody, state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_edit()
        if body.terminal is not None:
            if body.terminal not in TERMINALS:
                raise ProjectError(f"Unknown terminal: {body.terminal}")
            db.set_meta("inject_terminal", body.terminal)
        if body.wsl_distro is not None:
            db.set_meta("inject_wsl_distro", body.wsl_distro)
        if body.build_command is not None:
            db.set_meta("inject_build_command", body.build_command)
        if body.build_cwd is not None:
            db.set_meta("inject_build_cwd", body.build_cwd)
        if body.make_script is not None:
            db.set_meta("inject_make_script", body.make_script)
        if body.source_path is not None:
            db.set_meta("inject_source_path", body.source_path)
        db.commit()
        return {"ok": True}
    return _guard(go)


def _build_argv(terminal: str, command: str, cwd: str, distro: str) -> list[str]:
    """Construct the platform/terminal-appropriate argv for ``command``."""
    if terminal == "cmd":
        return ["cmd.exe", "/c", command]
    if terminal == "powershell":
        return ["powershell.exe", "-NoProfile", "-Command", command]
    if terminal == "wsl":
        inner = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
        argv = ["wsl.exe"]
        if distro:
            argv += ["-d", distro]
        argv += ["--", "sh", "-c", inner]
        return argv
    # bash (default)
    return ["bash", "-lc", command]


class BuildBody(BaseModel):
    command: Optional[str] = None     # overrides the stored build_command
    cwd: Optional[str] = None         # overrides the stored build_cwd
    terminal: Optional[str] = None    # overrides the stored terminal
    wsl_distro: Optional[str] = None


def _stream_build(build_id: str, argv: list[str], cwd: Optional[str],
                  terminal: str, bus: EventBus) -> None:
    """Run ``argv`` and fan its merged stdout/stderr over the ``build`` SSE event."""
    bus.publish("build", {"build_id": build_id, "event": "start",
                          "argv": argv, "terminal": terminal})
    # WSL handles its own `cd`; for other terminals run inside cwd directly.
    popen_cwd = None if (terminal == "wsl" or not cwd) else cwd
    try:
        proc = subprocess.Popen(
            argv, cwd=popen_cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        bus.publish("build", {"build_id": build_id, "event": "error",
                              "line": f"Failed to launch build: {e}"})
        bus.publish("build", {"build_id": build_id, "event": "done",
                              "returncode": -1})
        return
    with _builds_lock:
        _builds[build_id] = proc
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            bus.publish("build", {"build_id": build_id, "event": "log",
                                  "line": line.rstrip("\n")})
        proc.wait()
    finally:
        with _builds_lock:
            _builds.pop(build_id, None)
    bus.publish("build", {"build_id": build_id, "event": "done",
                          "returncode": proc.returncode})


@router.post("/projects/{test_project_id}/build")
def build(test_project_id: int, body: BuildBody,
          state: AppState = Depends(get_state),
          bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_open()
        terminal = (body.terminal or db.get_meta("inject_terminal", "bash"))
        if terminal not in TERMINALS:
            raise ProjectError(f"Unknown terminal: {terminal}")
        distro = body.wsl_distro if body.wsl_distro is not None \
            else (db.get_meta("inject_wsl_distro", "") or "")
        command = body.command if body.command is not None \
            else (db.get_meta("inject_build_command", "") or "")
        cwd = body.cwd if body.cwd is not None \
            else (db.get_meta("inject_build_cwd", "") or "")
        if not command.strip():
            raise ProjectError("No build command configured.")
        build_id = uuid.uuid4().hex
        argv = _build_argv(terminal, command, cwd, distro)
        threading.Thread(
            target=_stream_build,
            args=(build_id, argv, cwd, terminal, bus),
            name=f"build-{build_id[:8]}", daemon=True).start()
        return {"build_id": build_id, "terminal": terminal}
    return _guard(go)


@router.post("/build/{build_id}/cancel")
def cancel_build(build_id: str) -> dict:
    with _builds_lock:
        proc = _builds.get(build_id)
    if proc is None:
        raise HTTPException(status_code=404, detail="No such running build.")
    try:
        proc.terminate()
    except OSError:
        pass
    return {"build_id": build_id, "cancelling": True}

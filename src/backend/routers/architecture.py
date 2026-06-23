"""
Architecture / Workspace router (plan §3.2) — the must-have view's data backbone.

Models (list / create / rename / status / soft-delete / restore / activate),
the column schema, and paged port rows with single-cell edits.

Data model (from Phase 0): a model's rows are ``list[dict]`` where each row is
``{col_name: cell}`` and a cell is ``{"text": str, "widget_text"?: str,
"widget_style"?: str, "user_changed"?: bool, "is_purple"?: bool,
"last_func"?: str}``. The column schema is ``active_config`` =
``[(name, logic_key, visible, width), …]``. None of the Qt column classes are
needed here — ``logic_key`` strings carry column identity.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_bus, get_state
from ..events import EventBus
from ..security import require_token
from ..state import AppState, ProjectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["architecture"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Change history (ASPICE traceability log). Edits/adds/deletes append an
# append-only, tamper-evident entry keyed to the active release. The PyQt app
# exposed this as a single "View History"; the React app splits it into
# Model History (all entries) and Port History (filtered to one port).
# ---------------------------------------------------------------------------
def _record_history(state: AppState, description: str, model_name: str = "") -> None:
    """Best-effort append of one history entry. Never raises — a logging failure
    must not break the edit that triggered it."""
    db = state.db
    if db is None or not db.is_open:
        return
    try:
        from Application_Logic.Logic_File_Locking import FileLockManager
        db.add_history_entry(
            description=description,
            model_name=model_name,
            username=FileLockManager.get_username(),
            release_id=db.get_active_release_id(),
        )
    except Exception:
        logger.exception("Failed to record history entry")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CreateModelBody(BaseModel):
    name: str
    status: str = "In Work"
    copy_from_id: Optional[int] = None


class PatchModelBody(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    is_deleted: Optional[bool] = None


@router.get("/models")
def list_models(include_deleted: bool = False,
                state: AppState = Depends(get_state)) -> dict:
    def go():
        mgr = state.require_arch()
        db = state.require_open()
        active = mgr.get_active_model()
        active_id = active.id if active else None
        out = []
        for m in mgr.models:
            if m.is_deleted and not include_deleted:
                continue
            out.append({
                "id": m.id, "name": m.name, "status": m.status,
                "is_deleted": m.is_deleted, "sort_order": m.sort_order,
                "is_active": m.id == active_id,
                "row_count": db.get_row_count(m.id) if m.id is not None else 0,
            })
        return {"models": out, "active_model_id": active_id}
    return _guard(go)


@router.post("/models")
def create_model(body: CreateModelBody, state: AppState = Depends(get_state),
                 bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        mgr = state.require_arch()
        copy_idx = state.model_index_by_id(body.copy_from_id) if body.copy_from_id is not None else None
        m = mgr.create_model(body.name, body.status, copy_from_index=copy_idx)
        bus.publish("db-changed", {"reason": "model-created", "model_id": m.id})
        return {"id": m.id, "name": m.name, "status": m.status}
    return _guard(go)


@router.patch("/models/{model_id}")
def patch_model(model_id: int, body: PatchModelBody,
                state: AppState = Depends(get_state),
                bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        mgr = state.require_arch()
        idx = state.model_index_by_id(model_id)
        m = mgr.models[idx]
        if body.name is not None:
            m.name = body.name
        if body.status is not None:
            m.status = body.status
        if body.is_deleted is True:
            mgr.soft_delete_model(idx)
        elif body.is_deleted is False:
            mgr.restore_model(idx)
        else:
            mgr.save_registry()
        bus.publish("db-changed", {"reason": "model-updated", "model_id": model_id})
        return {"id": m.id, "name": m.name, "status": m.status, "is_deleted": m.is_deleted}
    return _guard(go)


@router.delete("/models/{model_id}")
def delete_model(model_id: int, state: AppState = Depends(get_state),
                 bus: EventBus = Depends(get_bus)) -> dict:
    """Permanently delete a model. Only empty models (no ports) may be hard
    deleted — non-empty models must use the soft-delete (PATCH is_deleted)
    path so their data can be restored."""
    def go():
        state.require_edit()
        mgr = state.require_arch()
        db = state.require_open()
        idx = state.model_index_by_id(model_id)
        m = mgr.models[idx]
        if m.id is not None and db.get_row_count(m.id) > 0:
            raise ProjectError(
                "Only empty models can be permanently deleted. "
                "Delete this model's ports first, or soft-delete it instead."
            )
        mgr.hard_delete_model(idx)
        bus.publish("db-changed", {"reason": "model-deleted", "model_id": model_id})
        return {"id": model_id, "deleted": True}
    return _guard(go)


@router.post("/models/{model_id}/activate")
def activate_model(model_id: int, state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        mgr = state.require_arch()
        idx = state.model_index_by_id(model_id)
        mgr.set_active_model(idx)
        bus.publish("db-changed", {"reason": "model-activated", "model_id": model_id})
        return state.status()
    return _guard(go)


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------
class ColumnSpec(BaseModel):
    name: str
    type: str
    visible: Optional[bool] = True  # True=Show, False=Hide, None=Auto (Init/Cyclic)
    width: int = 100


class PutColumnsBody(BaseModel):
    columns: list[ColumnSpec]
    # Columns renamed in this save, as {old_name: new_name}. Used to migrate the
    # cell key in every model's rows (cells are keyed by column name).
    renames: dict[str, str] = {}


def _columns_payload(db) -> dict:
    return {"columns": [
        {"name": n, "type": t, "visible": v, "width": w}
        for (n, t, v, w) in db.load_column_layout()
    ]}


# Stable col_name -> release_id binding for ReleaseResultColumns. Bound by id so
# a release rename never orphans the column (the modernization over the old
# name-encoded `Release_<name>_Result`).
RESULT_BINDINGS_KEY = "release_result_columns"


def _result_bindings(db) -> dict:
    import json
    raw = db.get_meta(RESULT_BINDINGS_KEY, "{}") or "{}"
    try:
        return {k: int(v) for k, v in json.loads(raw).items()}
    except Exception:
        return {}


def _result_columns_meta(db, rm) -> list:
    """Per result column: its bound release plus the flags the UI needs to derive
    values and gate editing (active release? release baselined?)."""
    bindings = _result_bindings(db)
    layout_names = {c[0] for c in db.load_column_layout()}
    active = rm.get_active_release() if rm is not None else None
    active_id = active.id if active else None
    out = []
    for col_name, rid in bindings.items():
        if col_name not in layout_names:
            continue
        rel = next((r for r in rm.releases if r.id == rid), None) if rm else None
        if rel is None:
            continue
        # Locked once the release is itself a baseline or has a baseline frozen
        # from it (matches the Qt ReleaseResultColumn locking rule).
        is_baselined = rel.is_baseline or any(
            r.is_baseline and not r.is_deleted and r.parent_release_name == rel.name
            for r in rm.releases)
        out.append({"name": col_name, "release_id": rid, "release_name": rel.name,
                    "is_active": rid == active_id, "is_baselined": bool(is_baselined)})
    return out


@router.get("/columns")
def get_columns(state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        rm = state.release_manager
        return {**_columns_payload(db), "result_columns": _result_columns_meta(db, rm)}
    return _guard(go)


@router.get("/columns/editor")
def get_columns_editor(state: AppState = Depends(get_state)) -> dict:
    """Everything the column customizer needs: the layout, the locked columns
    (computed from the active model's reviewed rows), and the addable types."""
    from Application_Logic.Logic_Column_Layout import compute_locked_columns, ADDABLE_TYPES

    def go():
        db = state.require_open()
        mgr = state.require_arch()
        layout = db.load_column_layout()
        active = mgr.get_active_model()
        rows = db.get_model_rows(active.id) if active and active.id is not None else []
        return {
            **_columns_payload(db),
            "locked": sorted(compute_locked_columns(layout, rows)),
            "addable_types": ADDABLE_TYPES,
        }
    return _guard(go)


@router.put("/columns")
def put_columns(body: PutColumnsBody, state: AppState = Depends(get_state),
                bus: EventBus = Depends(get_bus)) -> dict:
    from Application_Logic.Logic_Column_Layout import (
        validate_layout, migrate_rows, diff_layout,
    )

    def go():
        db = state.require_edit()
        mgr = state.require_arch()
        new_layout = [(c.name, c.type, c.visible, c.width) for c in body.columns]
        try:
            validate_layout(new_layout)
        except ValueError as e:
            raise ProjectError(str(e)) from e

        old_names = [c[0] for c in db.load_column_layout()]
        renames = {k: v for k, v in body.renames.items() if k != v}
        removed = diff_layout(old_names, [c[0] for c in new_layout], renames)

        # Migrate cell keys across every model (layout is project-global; cells
        # are per-model and keyed by column name).
        if renames or removed:
            for m in mgr.models:
                if m.id is None:
                    continue
                rows = db.get_model_rows(m.id)
                migrate_rows(rows, renames, removed)
                db.save_model_rows(m.id, rows)

        db.save_column_layout(new_layout)
        db.commit()
        bus.publish("db-changed", {"reason": "columns-updated"})
        return _columns_payload(db)
    return _guard(go)


# ---------------------------------------------------------------------------
# Ports (rows)
# ---------------------------------------------------------------------------
class CellUpdate(BaseModel):
    # Each value is either a scalar (sets/merges cell["text"]) or a full cell dict.
    updates: dict[str, Any]


@router.get("/models/{model_id}/ports")
def get_ports(model_id: int,
              offset: int = Query(0, ge=0),
              limit: int = Query(200, ge=1, le=5000),
              state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        state.model_index_by_id(model_id)   # validates existence
        rows = db.get_model_rows(model_id)
        page = rows[offset:offset + limit]
        return {
            "model_id": model_id,
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "rows": [{"row_index": offset + i, "cells": r} for i, r in enumerate(page)],
        }
    return _guard(go)


def _model_name(state: AppState, model_id: int) -> str:
    try:
        return state.require_arch().models[state.model_index_by_id(model_id)].name
    except Exception:
        return ""


def _apply_updates(cell_row: dict, updates: dict) -> dict:
    for col, val in updates.items():
        if isinstance(val, dict):
            cell_row[col] = val
        else:
            cell = cell_row.setdefault(col, {})
            cell["text"] = val
            # Mirror into widget_text for dropdown-style cells that use it, so
            # the displayed value and the stored value stay in sync.
            if "widget_text" in cell:
                cell["widget_text"] = val
    return cell_row


@router.patch("/models/{model_id}/ports/{row_index}")
def patch_port(model_id: int, row_index: int, body: CellUpdate,
               state: AppState = Depends(get_state),
               bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_table_edit()
        state.model_index_by_id(model_id)
        rows = db.get_model_rows(model_id)
        if not (0 <= row_index < len(rows)):
            raise ProjectError(f"No such row: {row_index}")
        # Snapshot the displayed text of each touched column BEFORE applying —
        # a shallow row copy shares the inner cell dicts, so _apply_updates would
        # otherwise mutate them in place and erase the "old" value.
        from Application_Logic.Logic_Architecture_Models import _cell_text
        before_text = {col: _cell_text(rows[row_index].get(col)) for col in body.updates}
        updated = _apply_updates(dict(rows[row_index]), body.updates)
        db.upsert_model_row(model_id, row_index, updated)
        db.commit()
        # Append one history entry per column whose displayed text actually
        # changed, mirroring the PyQt log format
        # "Row N -> <port> -> <col> -> <old> -> <new>".
        _state_cols, name_col = _port_columns(db)
        port = (_cell_text(updated.get(name_col)) if name_col else "") or "N/A"
        mname = _model_name(state, model_id)
        for col in body.updates:
            old_text = before_text[col]
            new_text = _cell_text(updated.get(col))
            if old_text == new_text:
                continue
            _record_history(
                state,
                f"Row {row_index + 1} -> {port} -> {col} -> {old_text} -> {new_text}",
                mname,
            )
        bus.publish("db-changed",
                    {"reason": "port-edited", "model_id": model_id, "row_index": row_index})
        return {"model_id": model_id, "row_index": row_index, "cells": updated}
    return _guard(go)


@router.post("/models/{model_id}/ports")
def add_port(model_id: int, body: Optional[CellUpdate] = None,
             state: AppState = Depends(get_state),
             bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_table_edit()
        state.model_index_by_id(model_id)
        rows = db.get_model_rows(model_id)
        new_row = _apply_updates({}, body.updates) if body else {}
        rows.append(new_row)
        db.save_model_rows(model_id, rows)   # re-indexes contiguously
        db.commit()
        idx = len(rows) - 1
        from Application_Logic.Logic_Architecture_Models import _cell_text
        _state_cols, name_col = _port_columns(db)
        port = (_cell_text(new_row.get(name_col)).strip() if name_col else "") or "N/A"
        _record_history(state, f"Row {idx + 1} -> {port} -> Added port",
                        _model_name(state, model_id))
        bus.publish("db-changed", {"reason": "port-added", "model_id": model_id, "row_index": idx})
        return {"model_id": model_id, "row_index": idx, "cells": new_row, "total": len(rows)}
    return _guard(go)


class BulkAddBody(BaseModel):
    # Each row is {col_name: scalar-or-cell}; scalars become {"text": value}.
    rows: list[dict[str, Any]]


@router.post("/models/{model_id}/ports/bulk")
def add_ports_bulk(model_id: int, body: BulkAddBody,
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    """Append many rows at once — the efficient import primitive. A Phase-2
    import wizard composes this with /api/jobs/fuzzy_rematch."""
    def go():
        db = state.require_table_edit()
        state.model_index_by_id(model_id)
        rows = db.get_model_rows(model_id)
        first = len(rows)
        for incoming in body.rows:
            rows.append(_apply_updates({}, incoming))
        db.save_model_rows(model_id, rows)
        db.commit()
        bus.publish("db-changed",
                    {"reason": "ports-imported", "model_id": model_id, "added": len(body.rows)})
        return {"model_id": model_id, "added": len(body.rows),
                "first_row_index": first, "total": len(rows)}
    return _guard(go)


@router.delete("/models/{model_id}/ports/{row_index}")
def delete_port(model_id: int, row_index: int,
                state: AppState = Depends(get_state),
                bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_table_edit()
        state.model_index_by_id(model_id)
        rows = db.get_model_rows(model_id)
        if not (0 <= row_index < len(rows)):
            raise ProjectError(f"No such row: {row_index}")
        from Application_Logic.Logic_Architecture_Models import _cell_text
        _state_cols, name_col = _port_columns(db)
        port = (_cell_text(rows[row_index].get(name_col)).strip() if name_col else "") or "N/A"
        del rows[row_index]
        db.save_model_rows(model_id, rows)   # re-indexes contiguously
        db.commit()
        _record_history(state, f"Row {row_index + 1} -> {port} -> Deleted port",
                        _model_name(state, model_id))
        bus.publish("db-changed", {"reason": "port-deleted", "model_id": model_id})
        return {"model_id": model_id, "total": len(rows)}
    return _guard(go)


# ---------------------------------------------------------------------------
# Port-state propagation (#8.2) — two-step: preview, then commit.
#
# Strict forward only: propagation fires solely on In Work → Released. Port state
# never moves backward, and a model going to a non-Released state (e.g. Retired)
# leaves its "In Work" ports untouched — only Released "pulls" In Work ports
# forward. Retired/Deleted ports are always left as-is. The cascade is NOT silent:
# the UI previews the affected ports and the user confirms/selects which ones
# follow. Core logic lives in ArchitectureManager.propagate_status_to_ports
# (kept general for the legacy app); the strict-forward gate lives here, the only
# entry point the React UI uses.
# ---------------------------------------------------------------------------
PROPAGATE_TARGET = "Released"


def _propagates(old_status: str, new_status: str) -> bool:
    """Strict-forward gate: only In Work → Released cascades onto ports."""
    return old_status == "In Work" and new_status == PROPAGATE_TARGET


class StateChangeBody(BaseModel):
    new_status: str
    selected_ports: Optional[list[str]] = None   # None = all eligible ports follow


def _port_columns(db) -> tuple[list[str], Optional[str]]:
    """(port_state_column_names, port_name_column) derived from the column schema.

    Port-state cols carry logic_key 'PortStateColumn'; the port-name col is the
    first 'Port Search'. Falls back to the conventional 'Port State' name.
    """
    layout = db.load_column_layout()
    state_cols = [n for (n, t, _v, _w) in layout if t == "PortStateColumn"] or ["Port State"]
    name_col = next((n for (n, t, _v, _w) in layout if t == "Port Search"), None)
    return state_cols, name_col


def _eligible_ports(db, model_id: int, state_cols: list[str], name_col: Optional[str]) -> list[dict]:
    from Application_Logic.Logic_Architecture_Models import _cell_text
    rows = db.get_model_rows(model_id)
    out = []
    for i, row in enumerate(rows):
        for col in state_cols:
            cell = row.get(col)
            if isinstance(cell, dict):
                cur = (cell.get("widget_text") or cell.get("text") or "").strip()
                if cur == "In Work":
                    out.append({
                        "row_index": i,
                        "port_name": _cell_text(row.get(name_col)) if name_col else "",
                        "column": col,
                    })
                    break
    return out


@router.post("/models/{model_id}/state/preview")
def preview_state_change(model_id: int, body: StateChangeBody,
                         state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        idx = state.model_index_by_id(model_id)
        old_status = state.require_arch().models[idx].status
        # Strict forward: only In Work → Released cascades onto ports.
        eligible = _propagates(old_status, body.new_status)
        state_cols, name_col = _port_columns(db)
        affected = _eligible_ports(db, model_id, state_cols, name_col) if eligible else []
        return {
            "model_id": model_id,
            "old_status": old_status,
            "new_status": body.new_status,
            "propagates": eligible,
            "port_state_columns": state_cols,
            "port_name_column": name_col,
            "affected_ports": affected,
        }
    return _guard(go)


@router.post("/models/{model_id}/state")
def commit_state_change(model_id: int, body: StateChangeBody,
                        state: AppState = Depends(get_state),
                        bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_table_edit()
        mgr = state.require_arch()
        idx = state.model_index_by_id(model_id)
        model = mgr.models[idx]
        old_status = model.status

        model.status = body.new_status
        mgr.save_registry()   # persist the status change

        # Strict forward: only In Work → Released pulls "In Work" ports along.
        if _propagates(old_status, body.new_status):
            state_cols, name_col = _port_columns(db)
            # Force a fresh load so propagation works off the DB's current rows
            # (the API edits rows directly, bypassing the in-memory data_cache).
            model.data_cache = None
            changed = mgr.propagate_status_to_ports(
                model, old_status, body.new_status,
                port_state_columns=tuple(state_cols),
                selected_ports=body.selected_ports,
                port_name_column=name_col,
            )
        else:
            changed = 0
        suffix = f" ({changed} port(s) followed)" if changed else ""
        _record_history(
            state,
            f"Model status changed: {old_status} -> {body.new_status}{suffix}",
            model.name,
        )
        bus.publish("db-changed",
                    {"reason": "model-state-changed", "model_id": model_id,
                     "new_status": body.new_status, "ports_changed": changed})
        return {
            "model_id": model_id,
            "old_status": old_status,
            "new_status": body.new_status,
            "ports_changed": changed,
        }
    return _guard(go)


# ---------------------------------------------------------------------------
# History read-back (newest-first). Model History = every entry for the active
# release; Port History = entries whose description references one port name.
# ---------------------------------------------------------------------------
@router.get("/history")
def get_history(model_name: Optional[str] = None,
                port: Optional[str] = None,
                state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        rel_id = db.get_active_release_id()
        entries = db.get_history(rel_id)          # id order (oldest first)
        if model_name:
            entries = [e for e in entries if (e.get("model") or "") == model_name]
        if port:
            needle = port.strip().lower()
            entries = [e for e in entries
                       if needle and needle in (e.get("description") or "").lower()]
        entries.reverse()                          # newest first for display
        return {"entries": entries, "release_id": rel_id}
    return _guard(go)

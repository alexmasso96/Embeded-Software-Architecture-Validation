"""
Baselines router (plan §3.2 / §7).

A baseline is a frozen snapshot of a release's active-model data + the column
layout at snapshot time. Creation mirrors the Qt ``handle_create_baseline``
headlessly: assemble ``layout_data`` (columns + settings + test-case design) and
``active_model_data`` (rows + per-model metadata), then
``ReleaseManager.create_baseline`` does the frozen DB writes.

    GET  /api/baselines              → list baselines (frozen, not deleted)
    POST /api/baselines              → create from active (or given) release + active model
    GET  /api/baselines/{id}         → snapshot layout + rows (read/"load" a baseline)
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_bus, get_state
from ..events import EventBus
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/baselines", tags=["baselines"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


class CreateBaselineBody(BaseModel):
    name: str
    release_id: Optional[int] = None     # default: the active release


def _settings(db) -> dict:
    return {
        "default_cyclicity": db.get_meta("default_cyclicity", "10"),
        "show_retired": db.get_meta("show_retired", True),
        "show_deleted": db.get_meta("show_deleted", False),
    }


@router.get("")
def list_baselines(state: AppState = Depends(get_state)) -> dict:
    def go():
        rm = state.require_releases()
        out = [
            {"id": r.id, "name": r.name, "parent_release_name": r.parent_release_name,
             "timestamp": r.timestamp, "description": r.description}
            for r in rm.releases if r.is_baseline and not r.is_deleted
        ]
        return {"baselines": out}
    return _guard(go)


@router.post("")
def create_baseline(body: CreateBaselineBody, state: AppState = Depends(get_state),
                    bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        db = state.require_edit()
        mgr_a = state.require_arch()
        rm = state.require_releases()

        if body.release_id is not None:
            release_idx = state.release_index_by_id(body.release_id)
        else:
            release_idx = rm.active_release_index
            if release_idx < 0:
                raise ProjectError("No active release to baseline.")

        active = mgr_a.get_active_model()
        if active is None or active.id is None:
            raise ProjectError("No active architecture model to snapshot.")

        layout_data = {
            "version": "2.0",
            "layout": [list(c) for c in db.load_column_layout()],
            "settings": _settings(db),
            "test_case_design": db.get_test_case_design(),
        }
        meta = db.get_model_metadata(active.id)
        active_model_data = {
            "rows": db.get_model_rows(active.id),
            "column_metadata": meta.get("column_metadata", {}) or {},
            "release_results": meta.get("release_results", {}) or {},
        }

        try:
            baseline = rm.create_baseline(release_idx, body.name, layout_data, active_model_data)
        except ValueError as e:
            raise ProjectError(str(e)) from e

        bus.publish("db-changed", {"reason": "baseline-created", "baseline_id": baseline.id})
        return {"id": baseline.id, "name": baseline.name,
                "parent_release_name": baseline.parent_release_name,
                "row_count": len(active_model_data["rows"])}
    return _guard(go)


SEARCH_TYPES = {"Port Search", "Function Search", "Variable Search"}


def _key_columns(layout: list) -> list[str]:
    """Compound row-identity key: TC. ID + the port/search column + its Match
    column. Multiple rows can share a TC. ID (different ops/ports), so we pair on
    the combination and disambiguate remaining duplicates by occurrence order."""
    names = [n for (n, _t, _v, _w) in layout]
    keys: list[str] = []
    if "TC. ID" in names:
        keys.append("TC. ID")
    for i, (n, t, _v, _w) in enumerate(layout):
        if t in SEARCH_TYPES:
            keys.append(n)
            if i + 1 < len(layout):       # the Match column sits right after
                keys.append(layout[i + 1][0])
            break
    # Fall back to all columns if the schema has no recognisable identity cols.
    return keys or names


def _diff_table(current: list, baseline: list, key_cols: list[str],
                compare_cols: list[str]) -> dict:
    """Row-level diff of two row-dict lists. Rows pair by compound key +
    occurrence order; cells compared by visible text. Returns ordered rows
    tagged added / removed / changed / unchanged plus a summary."""
    from collections import defaultdict
    from Application_Logic.Logic_Architecture_Models import _cell_text

    def key(row):
        return tuple(_cell_text(row.get(c)) for c in key_cols)

    buckets: dict = defaultdict(list)
    for i, r in enumerate(baseline):
        buckets[key(r)].append((i, r))
    used: set = set()
    seen: dict = defaultdict(int)
    rows: list = []

    for ci, cr in enumerate(current):
        k = key(cr)
        occ = seen[k]; seen[k] += 1
        bucket = buckets.get(k, [])
        if occ < len(bucket):
            bi, br = bucket[occ]
            used.add((k, occ))
            changed = [c for c in compare_cols
                       if _cell_text(cr.get(c)) != _cell_text(br.get(c))]
            rows.append({"status": "changed" if changed else "unchanged",
                         "key": list(k), "current_index": ci, "baseline_index": bi,
                         "changed_columns": changed,
                         "current": cr, "baseline": br})
        else:
            rows.append({"status": "added", "key": list(k), "current_index": ci,
                         "baseline_index": None, "changed_columns": [],
                         "current": cr, "baseline": None})

    for k, bucket in buckets.items():
        for occ, (bi, br) in enumerate(bucket):
            if (k, occ) not in used:
                rows.append({"status": "removed", "key": list(k), "current_index": None,
                             "baseline_index": bi, "changed_columns": [],
                             "current": None, "baseline": br})

    rows.sort(key=lambda r: (r["current_index"] is None,
                             r["current_index"] if r["current_index"] is not None
                             else r["baseline_index"]))
    summary = {s: 0 for s in ("added", "removed", "changed", "unchanged")}
    for r in rows:
        summary[r["status"]] += 1
    return {"rows": rows, "summary": summary}


@router.get("/{baseline_id}/diff")
def diff_baseline(baseline_id: int, model_id: Optional[int] = None,
                  state: AppState = Depends(get_state)) -> dict:
    """Compare the active model's current table against a baseline snapshot."""
    def go():
        db = state.require_open()
        rm = state.require_releases()
        mgr_a = state.require_arch()
        b = next((r for r in rm.releases if r.id == baseline_id and r.is_baseline), None)
        if b is None:
            raise ProjectError(f"No such baseline: {baseline_id}")

        if model_id is not None:
            mid = model_id
        else:
            active = mgr_a.get_active_model()
            if active is None or active.id is None:
                raise ProjectError("No active architecture model to compare.")
            mid = active.id

        layout = db.load_column_layout()
        compare_cols = [n for (n, _t, _v, _w) in layout]
        key_cols = _key_columns(layout)
        current = db.get_model_rows(mid)
        baseline = db.get_release_rows(baseline_id)

        diff = _diff_table(current, baseline, key_cols, compare_cols)
        return {"baseline_id": baseline_id, "baseline_name": b.name, "model_id": mid,
                "key_columns": key_cols, "columns": compare_cols, **diff}
    return _guard(go)


@router.get("/{baseline_id}")
def get_baseline(baseline_id: int, state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        rm = state.require_releases()
        b = next((r for r in rm.releases if r.id == baseline_id and r.is_baseline), None)
        if b is None:
            raise ProjectError(f"No such baseline: {baseline_id}")
        layout_blob = db.get_meta(f"baseline_layout_{baseline_id}")
        layout = json.loads(layout_blob) if layout_blob else {}
        rows = db.get_release_rows(baseline_id)
        return {
            "id": b.id,
            "name": b.name,
            "parent_release_name": b.parent_release_name,
            "layout": layout,
            "row_count": len(rows),
            "rows": [{"row_index": i, "cells": r} for i, r in enumerate(rows)],
        }
    return _guard(go)

"""
Import analysis router (plan §3.2, Excel/Rhapsody import).

The interactive import is a Phase-2 wizard that composes small primitives:
``/analyze`` (stateless inspection) and ``/read`` (parsed rows) give server-side
file access the browser can't have on network shares; plain Excel/CSV insertion
uses ``POST /api/models/{id}/ports/bulk`` + ``fuzzy_rematch``.

The one composite here is the **Rhapsody multi-model split** (``/rhapsody``):
a Rhapsody export embeds many packages in one path column, so it must fan out
into per-model row sets (create/append) in a single server-side step — the
browser can't replicate the P10-filter / operation-expansion / path→model logic.

    POST /api/import/analyze {file_path}
      → {format: "excel"|"rhapsody"|"csv", sheets?, path_col?, required_col?, ops_col?, models?}
    POST /api/import/rhapsody {file_path, col_mapping, path_col, ops_col?, required_col?}
      → {models: [{name, created, added}], total_models, total_added, model_ids}
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_bus, get_state
from ..events import EventBus
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/import", tags=["import"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _detect_ops_col(columns: list, path_col: str, required_col=None):
    """Guess the Rhapsody 'Operations' source column (expands into one row per op)."""
    for col in columns:
        if col in (path_col, required_col):
            continue
        if "operation" in str(col).lower():
            return col
    return None


class AnalyzeBody(BaseModel):
    file_path: str


@router.post("/analyze")
def analyze(body: AnalyzeBody) -> dict:
    path = body.file_path
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"No such file: {path}")

    from Application_Logic.Logic_Rhapsody_Import import (
        detect_rhapsody_format, read_file, get_model_preview,
        detect_required_interface_col,
    )

    try:
        is_rhapsody, path_col = detect_rhapsody_format(path)
        if is_rhapsody:
            columns, rows = read_file(path)
            required_col = detect_required_interface_col(columns, path_col)
            ops_col = _detect_ops_col(columns, path_col, required_col)
            preview = get_model_preview(rows, path_col, required_col)
            return {
                "format": "rhapsody",
                "path_col": path_col,
                "required_col": required_col,
                "ops_col": ops_col,
                "columns": columns,
                "models": [{"name": n, "port_count": c} for n, c in sorted(preview.items())],
            }

        if path.lower().endswith((".xlsx", ".xls")):
            import pandas as pd
            sheets = pd.ExcelFile(path).sheet_names
            return {"format": "excel", "sheets": list(sheets)}

        return {"format": "csv"}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — bad/locked file → 400 with the reason
        raise HTTPException(status_code=400, detail=f"Could not analyze file: {e}")


class ReadBody(BaseModel):
    file_path: str
    limit: int = 0  # 0 = all rows


@router.post("/read")
def read(body: ReadBody) -> dict:
    """Return the parsed (columns, rows) for a tabular import file so the Phase-2
    column-mapping UI can preview and build the bulk insert. The worker reads the
    file (the browser can't reach paths on network shares) — same rationale as
    ``/analyze``. Stateless; row insertion still goes through ``ports/bulk``."""
    path = body.file_path
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"No such file: {path}")
    from Application_Logic.Logic_Rhapsody_Import import read_file, detect_rhapsody_format
    try:
        columns, rows = read_file(path)
        is_rhapsody, path_col = detect_rhapsody_format(path)
        if body.limit and body.limit > 0:
            rows = rows[: body.limit]
        return {
            "columns": columns,
            "rows": rows,
            "total": len(rows),
            "is_rhapsody": is_rhapsody,
            "path_col": path_col,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")


class RhapsodyImportBody(BaseModel):
    file_path: str
    # {src_col -> table_col}; the path column is NOT included (it drives the split).
    col_mapping: dict[str, str]
    path_col: str
    ops_col: Optional[str] = None        # source col whose ops expand into rows
    required_col: Optional[str] = None   # source col that must be non-empty
    create_missing: bool = True          # create models that don't exist yet


@router.post("/rhapsody")
def import_rhapsody(body: RhapsodyImportBody,
                    state: AppState = Depends(get_state),
                    bus: EventBus = Depends(get_bus)) -> dict:
    """Split a Rhapsody export into per-model row sets and create/append each.

    The path column groups rows by package (``extract_model_name`` = 3rd path
    segment); ``build_import_data`` applies the P10 filter, drops rows missing the
    required-interface value, and expands multi-operation cells into one row each.
    Each resulting model is created if missing (else appended to). Returns the
    affected model ids so the caller can fire a single ``fuzzy_rematch`` over them.
    """
    if not os.path.exists(body.file_path):
        raise HTTPException(status_code=404, detail=f"No such file: {body.file_path}")

    from Application_Logic.Logic_Rhapsody_Import import read_file, build_import_data

    def go():
        db = state.require_edit()
        mgr = state.require_arch()
        try:
            _columns, rows = read_file(body.file_path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

        model_data = build_import_data(
            rows, body.col_mapping, body.path_col,
            ops_col=body.ops_col, required_col=body.required_col,
        )
        if not model_data:
            raise ProjectError("No importable rows found (no P10_SW_Arch_Public rows matched).")

        by_name = {m.name: m for m in mgr.models if not m.is_deleted}
        summary, model_ids = [], []
        for name in sorted(model_data):
            new_rows = model_data[name]
            model = by_name.get(name)
            created = False
            if model is None:
                if not body.create_missing:
                    continue
                model = mgr.create_model(name, "In Work")
                by_name[name] = model
                created = True
            existing = db.get_model_rows(model.id)
            existing.extend(new_rows)
            db.save_model_rows(model.id, existing)
            summary.append({"name": name, "created": created, "added": len(new_rows)})
            model_ids.append(model.id)

        db.commit()
        bus.publish("db-changed", {"reason": "rhapsody-imported",
                                   "models": len(summary)})
        return {
            "models": summary,
            "total_models": len(summary),
            "total_added": sum(s["added"] for s in summary),
            "model_ids": model_ids,
        }

    return _guard(go)

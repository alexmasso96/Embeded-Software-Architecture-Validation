"""
Test Case Design router (plan §3.2): template settings, live preview, condition
autocomplete, and HLT Markdown export.

    GET  /api/testdesign              → {project_title, design_template, operation_grouping}
    PUT  /api/testdesign              → persist the three template settings
    POST /api/testdesign/preview      → render one effective row to {title, body} + count
    GET  /api/testdesign/suggestions  → condition autocomplete completions + prefix
    POST /api/testdesign/export       → write <Model>_Test_Case_Design.md files

All template evaluation / grouping reuses the Qt-free pure helpers in
Logic_TestCase_Design, so the API and the legacy Qt tab render identically. The
preview/export read the active (or requested) model's stored rows and the
project column layout; the operation-grouping mode collapses ports the same way
the generated files do.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from Application_Logic import Logic_TestCase_Design as tcd

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/testdesign", tags=["testdesign"],
                   dependencies=[Depends(require_token)])

DEFAULT_GROUPING = "grouped"


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _resolve_model_id(state: AppState, model_id: Optional[int]) -> int:
    if model_id is not None:
        state.model_index_by_id(model_id)   # validate
        return model_id
    mgr = state.require_arch()
    mid = mgr.active_model_id
    if mid is None:
        raise ProjectError("No active architecture model.")
    return mid


def _model_name(state: AppState, model_id: int) -> str:
    mgr = state.require_arch()
    for m in mgr.models:
        if m.id == model_id:
            return m.name
    return ""


def _col_types(layout) -> dict:
    """name → logic type, for the ignored-column / port-state resolution."""
    return {entry[0]: entry[1] for entry in layout}


def _resolved_columns(state: AppState, model_id: int):
    """(layout, port_col, ops_col, col_types) for a model's grouping/render."""
    db = state.require_open()
    layout = db.load_column_layout()
    ops_col = tcd.resolve_ops_column(layout, db.get_meta("operations_column_name"))
    port_col = tcd.resolve_port_column(layout, db.get_meta("port_column_name"), ops_col)
    return layout, port_col, ops_col, _col_types(layout)


def _effective_rows(state: AppState, model_id: int, grouping: str):
    layout, port_col, ops_col, col_types = _resolved_columns(state, model_id)
    raw_rows = state.require_open().get_model_rows(model_id)
    rows = tcd.build_effective_rows(raw_rows, grouping, port_col, ops_col)
    return rows, col_types


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class TemplateSettings(BaseModel):
    project_title: str = ""
    design_template: str = ""
    operation_grouping: str = DEFAULT_GROUPING


@router.get("")
def get_settings(state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        data = db.get_test_case_design()
        return {
            "project_title": data.get("project_title", "") or "",
            "design_template": data.get("design_template", "") or "",
            "operation_grouping": data.get("operation_grouping") or DEFAULT_GROUPING,
        }
    return _guard(go)


@router.put("")
def set_settings(body: TemplateSettings, state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_edit()
        grouping = body.operation_grouping if body.operation_grouping in ("grouped", "independent") else DEFAULT_GROUPING
        db.set_test_case_design({
            "project_title": body.project_title,
            "design_template": body.design_template,
            "operation_grouping": grouping,
        })
        db.commit()
        return {"project_title": body.project_title,
                "design_template": body.design_template,
                "operation_grouping": grouping}
    return _guard(go)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
class PreviewBody(BaseModel):
    project_title: str = ""
    design_template: str = ""
    operation_grouping: str = DEFAULT_GROUPING
    model_id: Optional[int] = None
    release_id: Optional[int] = None
    row_index: int = 0


@router.post("/preview")
def preview(body: PreviewBody, state: AppState = Depends(get_state)) -> dict:
    def go():
        mid = _resolve_model_id(state, body.model_id)
        grouping = body.operation_grouping if body.operation_grouping in ("grouped", "independent") else DEFAULT_GROUPING
        rows, col_types = _effective_rows(state, mid, grouping)
        unit_label = "Port" if grouping == "grouped" else "Row"
        total = len(rows)
        if total == 0:
            return {"row_count": 0, "unit_label": unit_label, "index": 0,
                    "title": "", "body": "", "status": "empty",
                    "message": "No rows in this architecture model."}

        idx = max(0, min(body.row_index, total - 1))
        row_bind_data = rows[idx]
        renderable, reason = tcd.is_row_renderable(row_bind_data, col_types)
        if not renderable:
            msg = (f"{unit_label} {idx + 1} is empty. Enter data in the table to see a preview."
                   if reason == "empty"
                   else f"{unit_label} {idx + 1} Port State is '{reason}'. "
                        f"Test cases are not generated for Retired or Deleted ports.")
            return {"row_count": total, "unit_label": unit_label, "index": idx,
                    "title": "", "body": "", "status": reason, "message": msg}

        model_name = _model_name(state, mid)
        title, design = tcd.render_template(
            body.project_title, body.design_template, row_bind_data, model_name)
        return {"row_count": total, "unit_label": unit_label, "index": idx,
                "title": title, "body": design, "status": "ok", "message": ""}
    return _guard(go)


# ---------------------------------------------------------------------------
# Autocomplete suggestions
# ---------------------------------------------------------------------------
@router.get("/suggestions")
def suggestions(line_text: str = Query(""),
                model_id: Optional[int] = None,
                state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        mid = _resolve_model_id(state, model_id)
        layout = db.load_column_layout()
        # Visible columns are the ones the user templates against. "Model" is a
        # synthetic token injected at render time (the active model's name), so
        # surface it in autocomplete too — otherwise [Model] is undiscoverable.
        active_columns = [entry[0] for entry in layout if entry[2] is not False]
        if not any(c.lower() == "model" for c in active_columns):
            active_columns.append("Model")

        rows = db.get_model_rows(mid)

        def unique_values(col_name):
            if not col_name:
                return []
            out, seen = [], set()
            for r in rows:
                cell = r.get(col_name)
                val = ""
                if isinstance(cell, dict):
                    val = cell.get("widget_text") or cell.get("text") or ""
                val = tcd.strip_percentage_suffix(str(val)).strip()
                if val:
                    quoted = f"'{val}'"
                    if quoted not in seen:
                        seen.add(quoted)
                        out.append(quoted)
            return out

        completions, prefix = tcd.get_condition_suggestions_and_prefix(
            line_text, active_columns, unique_values)

        # Fallback: outside an #if condition the logic layer returns nothing,
        # but the legacy Qt tab still offered plain column-name autocomplete on
        # an open '['. Detect an unclosed bracket on the line and surface the
        # active columns so standard column suggestions keep working.
        if not completions:
            last_open = line_text.rfind("[")
            if last_open != -1 and last_open > line_text.rfind("]"):
                completions = [f"[{c}]" for c in active_columns]
                prefix = line_text[last_open:]

        return {"completions": completions, "prefix": prefix}
    return _guard(go)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
class ExportBody(BaseModel):
    project_title: str = ""
    design_template: str = ""
    operation_grouping: str = DEFAULT_GROUPING
    scope: str = "current"          # "current" | "all"
    model_id: Optional[int] = None


@router.post("/export")
def export(body: ExportBody, state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        if not state.project_path:
            raise ProjectError("Save the project before exporting test cases.")

        grouping = body.operation_grouping if body.operation_grouping in ("grouped", "independent") else DEFAULT_GROUPING

        if body.scope == "all":
            model_ids = [m["id"] for m in db.get_all_models() if not m.get("is_deleted")]
        else:
            model_ids = [_resolve_model_id(state, body.model_id)]

        output_dir = os.path.join(os.path.dirname(state.project_path), "Test Case Design")
        os.makedirs(output_dir, exist_ok=True)

        files = []
        for mid in model_ids:
            rows, col_types = _effective_rows(state, mid, grouping)
            model_name = _model_name(state, mid) or f"Model_{mid}"
            markdown = tcd.build_model_markdown(
                model_name, rows, body.project_title, body.design_template, col_types)
            if markdown is None:
                continue
            filename = f"{tcd.sanitize_filename(model_name)}_Test_Case_Design.md"
            file_path = os.path.join(output_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            files.append(filename)

        return {"output_dir": output_dir, "files": files, "file_count": len(files)}
    return _guard(go)

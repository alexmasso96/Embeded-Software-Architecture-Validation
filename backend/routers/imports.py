"""
Import analysis router (plan §3.2, Excel/Rhapsody import).

The interactive import is a Phase-2 wizard that composes small primitives — this
stateless endpoint gives it server-side file inspection (needed for files on
network shares the browser can't read), and the actual row insertion uses
``POST /api/models/{id}/ports/bulk`` + the ``fuzzy_rematch`` job. There is no
monolithic server-side "import" operation by design.

    POST /api/import/analyze {file_path}
      → {format: "excel"|"rhapsody"|"csv", sheets?, path_col?, models?}
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..security import require_token

router = APIRouter(prefix="/api/import", tags=["import"],
                   dependencies=[Depends(require_token)])


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
            preview = get_model_preview(rows, path_col, required_col)
            return {
                "format": "rhapsody",
                "path_col": path_col,
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

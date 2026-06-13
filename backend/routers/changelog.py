"""
Change Log router (plan §3.2): the side-by-side release diff + AI summary.

Diffs are computed by the ``release_diff`` job (which persists per-file diffs +
the model's diff hash). These read-only endpoints surface them:

    GET /api/changelog?model_id=                 → diff hash, file list, AI summary
    GET /api/changelog/diff?file=&model_id=      → one file's aligned side-by-side diff

Aligning reuses the Phase-0 pure ``parse_and_align_diff``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from Application_Logic.Logic_Change_Log_Tab import parse_and_align_diff

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/changelog", tags=["changelog"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _resolve_model_id(state: AppState, model_id: Optional[int]) -> int:
    if model_id is not None:
        state.model_index_by_id(model_id)
        return model_id
    mid = state.require_arch().active_model_id
    if mid is None:
        raise ProjectError("No active architecture model.")
    return mid


def _diff_hash(db, model_id: int) -> Optional[str]:
    meta = db.get_model_mindmap_meta(model_id)
    return meta.get("diff_hash") if meta else None


@router.get("")
def changelog(model_id: Optional[int] = None,
              state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        mid = _resolve_model_id(state, model_id)
        diff_hash = _diff_hash(db, mid)
        if not diff_hash:
            return {"model_id": mid, "diff_hash": None, "files": [], "ai_change_log": ""}
        diffs = db.get_code_diffs(mid, diff_hash)
        ai_log = db.get_model_metadata(mid).get("ai_change_log", "")
        return {
            "model_id": mid,
            "diff_hash": diff_hash,
            "files": [{"file_path": d["file_path"], "status": d["status"]} for d in diffs],
            "ai_change_log": ai_log or "",
        }
    return _guard(go)


@router.get("/diff")
def file_diff(file: str = Query(..., min_length=1), model_id: Optional[int] = None,
              state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        mid = _resolve_model_id(state, model_id)
        diff_hash = _diff_hash(db, mid)
        if not diff_hash:
            raise ProjectError("No diffs computed for this model — run the release_diff job.")
        match = next((d for d in db.get_code_diffs(mid, diff_hash)
                      if d["file_path"] == file), None)
        if match is None:
            raise ProjectError(f"No diff for file: {file}")
        old_aligned, new_aligned = parse_and_align_diff(match["unified_diff"])
        return {
            "model_id": mid,
            "file_path": file,
            "status": match["status"],
            # Each side is a list of [line_text, line_type] pairs.
            "old": [[t, k] for (t, k) in old_aligned],
            "new": [[t, k] for (t, k) in new_aligned],
        }
    return _guard(go)

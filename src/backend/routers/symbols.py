"""
Symbols router (plan §3.2): fuzzy candidate lookup feeding the match-picker.

    GET /api/symbols?q=<port>&kind=function|variable|any&limit=10[&elf_hash=...]

Candidates come from the active release's ELF symbols stored in the DB (or an
explicit ``elf_hash``). Each candidate is ``{"name", "score"}`` — the same
``Name (NN%)`` data the Qt match dropdown showed, minus the widget.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api", tags=["symbols"],
                   dependencies=[Depends(require_token)])


@router.get("/symbols")
def symbols(q: str = Query(..., min_length=1),
            kind: str = Query("any", pattern="^(function|variable|any)$"),
            limit: int = Query(10, ge=1, le=50),
            elf_hash: Optional[str] = None,
            state: AppState = Depends(get_state)) -> dict:
    try:
        state.require_open()
        ehash = elf_hash or state.active_elf_hash()
        if not ehash:
            # No ELF imported for the active release — empty candidate list, not an error.
            return {"query": q, "kind": kind, "elf_hash": None, "candidates": []}
        matcher = state.get_symbol_matcher(ehash)
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if kind == "function":
        pairs = matcher.find_top_function_matches(q, limit=limit)
    elif kind == "variable":
        pairs = matcher.find_top_variable_matches(q, limit=limit)
    else:
        pairs = matcher.find_top_matches(q, limit=limit)

    return {
        "query": q,
        "kind": kind,
        "elf_hash": ehash,
        "candidates": [{"name": n, "score": s} for n, s in pairs],
    }

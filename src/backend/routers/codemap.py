"""
Code Map + source router (plan §3.2).

    GET /api/codemap                        → function list + counts for a model/release map
    GET /api/codemap/graph?fn=&back=&fwd=   → depth-limited call-graph nodes + edges
    GET /api/codemap/function/{name}        → function details (callers/callees/globals/tooltip)
    GET /api/source/function/{name}         → extracted source block for a function

Reads the stored CodeMap (`db.get_model_code_map`) and the release source store
(`db.read_release_source_file`); the heavy *build* is the `build_code_map` job.
Graph traversal, symbol tooltip, and source extraction reuse the Phase-0 pure
functions in Logic_Code_Map_Tab so the API and the (legacy) Qt tab share one
implementation.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from Application_Logic.Logic_Code_Map_Tab import (
    MAX_GRAPH_NODES,
    build_callers_map,
    compute_graph_levels,
    describe_symbol,
    extract_function_block_by_line,
)

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api", tags=["codemap"],
                   dependencies=[Depends(require_token)])


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


def _dataset(state: AppState, model_id: Optional[int], release_id: Optional[int]) -> dict:
    db = state.require_open()
    mid = _resolve_model_id(state, model_id)
    code_map = db.get_model_code_map(mid, release_id=release_id)
    if not code_map or "functions" not in code_map:
        raise ProjectError("No Code Map for this model/release — run the build_code_map job.")
    return code_map


def _function_names(dataset: dict) -> list[str]:
    """Real functions only — mirror the Qt list: drop compiler internals and
    names that are actually data/type symbols, sorted."""
    from core.elf_parser import keep_function_name
    data_names = set(dataset.get("global_variables", {})) | set(dataset.get("structures", {}))
    return [n for n in sorted(dataset["functions"])
            if keep_function_name(n) and n not in data_names]


def _matched_globals(dataset: dict, fname: str) -> list[dict]:
    """Prefix-heuristic global match (same rule as the Qt details panel)."""
    prefix = fname.split('_')[0] + '_' if '_' in fname else fname[:3]
    out = []
    for var_name, var_type in dataset.get("global_variables", {}).items():
        if var_name.startswith(prefix):
            out.append({"name": var_name, "type": var_type})
    return sorted(out, key=lambda g: g["name"])[:50]


@router.get("/codemap")
def codemap(model_id: Optional[int] = None, release_id: Optional[int] = None,
            state: AppState = Depends(get_state)) -> dict:
    def go():
        ds = _dataset(state, model_id, release_id)
        names = _function_names(ds)
        return {
            "model_id": _resolve_model_id(state, model_id),
            "function_count": len(names),
            "functions": names,
            "global_count": len(ds.get("global_variables", {})),
            "define_count": len(ds.get("defines", {})),
        }
    return _guard(go)


@router.get("/codemap/graph")
def codemap_graph(fn: Optional[str] = None,
                  back: int = Query(1, ge=1, le=5),
                  fwd: int = Query(1, ge=1, le=5),
                  model_id: Optional[int] = None, release_id: Optional[int] = None,
                  state: AppState = Depends(get_state)) -> dict:
    def go():
        ds = _dataset(state, model_id, release_id)
        functions = ds["functions"]
        names = _function_names(ds)
        if not names:
            return {"focus": None, "nodes": [], "edges": [], "total_nodes": 0, "truncated": False}
        focus = fn if (fn and fn in functions) else ("main" if "main" in names else names[0])

        callers_map = build_callers_map(functions)
        level_nodes, node_levels, total = compute_graph_levels(
            ds, callers_map, focus, back, fwd)

        nodes = []
        for name, lvl in node_levels.items():
            ntype = "center" if lvl == 0 else ("caller" if lvl < 0 else "callee")
            nodes.append({"name": name, "level": lvl, "type": ntype})

        edges = []
        for u in node_levels:
            for v in functions.get(u, {}).get("calls", []):
                if v in node_levels:
                    kind = "callee" if node_levels[v] >= 0 else "caller"
                    edges.append({"source": u, "target": v, "kind": kind})

        return {
            "focus": focus,
            "nodes": nodes,
            "edges": edges,
            "total_nodes": total,
            "truncated": total > MAX_GRAPH_NODES,
            "max_nodes": MAX_GRAPH_NODES,
        }
    return _guard(go)


@router.get("/codemap/function/{name}")
def codemap_function(name: str, model_id: Optional[int] = None,
                     release_id: Optional[int] = None,
                     state: AppState = Depends(get_state)) -> dict:
    def go():
        ds = _dataset(state, model_id, release_id)
        functions = ds["functions"]
        if name not in functions:
            raise ProjectError(f"No such function in the Code Map: {name}")
        f = functions[name]
        callers = sorted(build_callers_map(functions).get(name, []))
        return {
            "name": name,
            "address": f.get("address", 0),
            "size": f.get("size", 0),
            "signature": f.get("signature"),
            "return_type": f.get("return_type"),
            "file": f.get("file"),
            "line_start": f.get("line_start"),
            "callers": callers,
            "callees": f.get("calls", []),
            "globals": _matched_globals(ds, name),
            "tooltip_html": describe_symbol(ds, name),
        }
    return _guard(go)


@router.get("/source/function/{name}")
def source_function(name: str, model_id: Optional[int] = None,
                    release_id: Optional[int] = None,
                    state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        ds = _dataset(state, model_id, release_id)
        f = ds["functions"].get(name)
        if not f:
            raise ProjectError(f"No such function in the Code Map: {name}")
        rel_path = f.get("file")
        line_start = f.get("line_start", 1) or 1
        if not rel_path:
            return {"name": name, "file": None, "found": False, "source": "",
                    "reason": "no source-file metadata"}

        rid = release_id if release_id is not None else db.get_active_release_id()
        content = None
        if rid is not None and db.has_release_source(rid):
            norm = rel_path.replace(os.sep, "/")
            content = db.read_release_source_file(rid, norm)
            if content is None:
                base = os.path.basename(norm)
                for entry in db.list_release_source_files(rid):
                    if os.path.basename(entry["rel_path"]) == base:
                        content = db.read_release_source_file(rid, entry["rel_path"])
                        break
        if content is None:
            return {"name": name, "file": rel_path, "line_start": line_start,
                    "found": False, "source": "",
                    "reason": "source not imported for this release"}

        block = extract_function_block_by_line(content, line_start)
        return {"name": name, "file": rel_path, "line_start": line_start,
                "found": True, "source": block}
    return _guard(go)

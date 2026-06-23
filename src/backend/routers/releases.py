"""
Releases router (plan §3.2): list / create / activate / rename / delete.

Releases are real software releases (newest first; create inserts at index 0).
Baselines are frozen snapshots — they show up in the list with ``is_baseline``
but are filtered out of the source/release pickers (``selectable``). Baseline
*creation* needs the layout + active-model snapshot and lands in a follow-up
(it maps to plan §3's ``create_baseline`` job).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_bus, get_jobs, get_state
from ..events import EventBus
from ..jobs import JobManager
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/releases", tags=["releases"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


class CreateReleaseBody(BaseModel):
    name: str
    description: str = ""
    copy_from_active: bool = False
    baseline_previous: bool = False


class RenameReleaseBody(BaseModel):
    name: str


class BranchReleaseBody(BaseModel):
    name: str
    description: str = ""


class ImportSourceBody(BaseModel):
    source_dir: str


def _release_view(rm, db, r, active_id) -> dict:
    has_source = db.has_release_source(r.id) if r.id is not None else False
    return {
        "id": r.id,
        "name": r.name,
        "is_baseline": r.is_baseline,
        "is_deleted": r.is_deleted,
        "parent_release_name": r.parent_release_name,
        "description": r.description,
        "timestamp": r.timestamp,
        "elf_hash": r.elf_hash,
        "elf_path": r.elf_path,
        "has_source": has_source,
        "is_active": r.id == active_id,
        # 'selectable' = a real release offered in pickers (#2E).
        "selectable": (not r.is_baseline and not r.is_deleted),
    }


def _compute_grid(releases) -> dict:
    """Lay every release (incl. baselines AND soft-deleted ones) onto stable
    integer grid coordinates so the lineage tree never shifts when "Show Deleted"
    is toggled — deleted nodes simply leave an empty cell behind.

    Layout rules (design §2):
      * mainline successor (the first non-baseline child) continues straight up:
        ``(x, y-1)``;
      * additional release forks fan out to the right;
      * baseline children fan out to the left at the parent's row.
    Coordinates are computed over the *full* node set (order-stable), then
    normalised so the minimum x and y are both 0. Returns ``{id: (grid_x, grid_y)}``.
    """
    by_name = {r.name: r for r in releases}
    # Children keyed by parent name, in stable creation order (timestamp, id).
    children: dict = {}
    roots = []
    for r in releases:
        parent = r.parent_release_name
        if parent and parent in by_name and by_name[parent] is not r:
            children.setdefault(parent, []).append(r)
        else:
            roots.append(r)

    def _sort_key(r):
        return (r.timestamp or "", r.id if r.id is not None else 0)

    for kids in children.values():
        kids.sort(key=_sort_key)
    roots.sort(key=_sort_key)

    def _layout(node, x, y, out):
        out[node.id] = (x, y)
        kids = children.get(node.name, [])
        releases_kids = [k for k in kids if not k.is_baseline]
        baseline_kids = [k for k in kids if k.is_baseline]
        for i, k in enumerate(releases_kids):
            _layout(k, x + i, y - 1, out)     # mainline up; extra forks rightward
        for j, k in enumerate(baseline_kids):
            _layout(k, x - 1 - j, y, out)     # baselines fan to the left

    # Pack each root tree into its own horizontal band (1-column gap between trees).
    coords: dict = {}
    running = 0
    for root in roots:
        rel: dict = {}
        _layout(root, 0, 0, rel)
        if not rel:
            continue
        min_x = min(p[0] for p in rel.values())
        max_x = max(p[0] for p in rel.values())
        offset = running - min_x
        for nid, (x, y) in rel.items():
            coords[nid] = (x + offset, y)
        running = offset + max_x + 2

    if coords:
        min_y = min(y for (_x, y) in coords.values())
        for nid, (x, y) in list(coords.items()):
            coords[nid] = (x, y - min_y)
    return coords


@router.get("/lineage")
def release_lineage(state: AppState = Depends(get_state)) -> dict:
    """Parent-child DAG of all releases + baselines with stable grid coordinates.

    Always returns *every* node (including soft-deleted ones, flagged via
    ``is_deleted``) so the frontend can hide deleted nodes while preserving their
    grid cells. Read-only — works in view mode.
    """
    def go():
        rm = state.require_releases()
        db = state.require_open()
        active = rm.get_active_release()
        active_id = active.id if active else None
        # Flush the active release's in-memory edits so its row_count is current.
        rm.flush_active_release_data()
        grid = _compute_grid(rm.releases)
        nodes = []
        for r in rm.releases:
            gx, gy = grid.get(r.id, (0, 0))
            row_count = len(db.get_release_rows(r.id)) if r.id is not None else 0
            nodes.append({
                "id": r.id,
                "name": r.name,
                "is_baseline": r.is_baseline,
                "is_deleted": r.is_deleted,
                "is_active": r.id == active_id,
                "parent_release_name": r.parent_release_name,
                "description": r.description,
                "timestamp": r.timestamp,
                "row_count": row_count,
                "elf_hash": r.elf_hash,
                "has_source": db.has_release_source(r.id) if r.id is not None else False,
                "grid_x": gx,
                "grid_y": gy,
            })
        return {"active_release_id": active_id, "nodes": nodes}
    return _guard(go)


@router.get("")
def list_releases(include_deleted: bool = False,
                  state: AppState = Depends(get_state)) -> dict:
    def go():
        rm = state.require_releases()
        db = state.require_open()
        active = rm.get_active_release()
        active_id = active.id if active else None
        out = [_release_view(rm, db, r, active_id)
               for r in rm.releases if include_deleted or not r.is_deleted]
        return {"releases": out, "active_release_id": active_id}
    return _guard(go)


@router.post("")
def create_release(body: CreateReleaseBody, state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        try:
            r = rm.create_release(
                body.name, description=body.description,
                copy_from_active=body.copy_from_active,
                baseline_previous=body.baseline_previous,
            )
        except ValueError as e:
            raise ProjectError(str(e)) from e
        bus.publish("db-changed", {"reason": "release-created", "release_id": r.id})
        return {"id": r.id, "name": r.name}
    return _guard(go)


@router.post("/{release_id}/activate")
def activate_release(release_id: int, state: AppState = Depends(get_state),
                     bus: EventBus = Depends(get_bus)) -> dict:
    """Activate a release/baseline AND swap the table data to match.

    The React table reads architecture_rows (per active model); releases store
    their snapshot in release_rows. Activation must move the data so the grid
    actually reflects the chosen release:
      1. Flush the active model's current rows back into the *previous* active
         release's snapshot (skipped if that release is a frozen baseline).
      2. Load the *target* release's snapshot into the active model's
         architecture_rows verbatim. The snapshot is authoritative — seeding a
         release from the working set happens at create time (copy_from_active),
         not here.
    """
    def go():
        db = state.require_edit()
        rm = state.require_releases()
        mgr_a = state.require_arch()
        idx = state.release_index_by_id(release_id)

        prev = rm.get_active_release()
        target = rm.releases[idx]
        model = mgr_a.get_active_model()

        if model is not None and model.id is not None and (prev is None or prev.id != target.id):
            # 1. Flush working rows → previous release snapshot.
            if prev is not None and prev.id is not None and not prev.is_baseline:
                db.save_release_rows(prev.id, db.get_model_rows(model.id))
            # 2. Load target snapshot → working rows (verbatim, even if empty).
            db.save_model_rows(model.id, db.get_release_rows(target.id))
            # Drop the stale in-memory cache so non-API readers reload from DB.
            model.data_cache = None

        rm.set_active_release(idx)
        db.commit()
        bus.publish("db-changed", {"reason": "release-activated", "release_id": release_id})
        return state.status()
    return _guard(go)


@router.patch("/{release_id}")
def rename_release(release_id: int, body: RenameReleaseBody,
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        ok, msg = rm.rename_release(idx, body.name)
        if not ok:
            raise ProjectError(msg)
        bus.publish("db-changed", {"reason": "release-renamed", "release_id": release_id})
        return {"id": release_id, "name": body.name}
    return _guard(go)


@router.delete("/{release_id}")
def delete_release(release_id: int, comment: str = "",
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        ok, msg = rm.delete_release(idx, deletion_comment=comment)
        if not ok:
            raise ProjectError(msg)
        bus.publish("db-changed", {"reason": "release-deleted", "release_id": release_id})
        return {"id": release_id, "result": msg}
    return _guard(go)


@router.post("/{release_id}/restore")
def restore_release(release_id: int, state: AppState = Depends(get_state),
                    bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        ok, msg = rm.restore_release(idx)
        if not ok:
            raise ProjectError(msg)
        bus.publish("db-changed", {"reason": "release-restored", "release_id": release_id})
        return {"id": release_id, "result": msg}
    return _guard(go)


@router.post("/{release_id}/branch")
def branch_release(release_id: int, body: BranchReleaseBody,
                   state: AppState = Depends(get_state),
                   bus: EventBus = Depends(get_bus)) -> dict:
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        try:
            r = rm.branch_release(idx, body.name, description=body.description)
        except ValueError as e:
            raise ProjectError(str(e)) from e
        bus.publish("db-changed", {"reason": "release-branched",
                                   "release_id": r.id, "parent_release_id": release_id})
        return {"id": r.id, "name": r.name,
                "parent_release_name": r.parent_release_name}
    return _guard(go)


@router.post("/{release_id}/result-column")
def add_result_column(release_id: int, state: AppState = Depends(get_state),
                      bus: EventBus = Depends(get_bus)) -> dict:
    """Add a release-result column for this release (at most one per release),
    plus a single 'Last Result' column if missing. Values are derived per-row
    from model status + the port's Review/State; only recorded verdicts persist."""
    import json
    from Application_Logic.Logic_Release_Results import result_column_name
    from backend.routers.architecture import RESULT_BINDINGS_KEY, _result_bindings

    def go():
        db = state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        rel = rm.releases[idx]

        bindings = _result_bindings(db)
        if release_id in bindings.values():
            raise ProjectError(f"A result column for '{rel.name}' already exists.")

        layout = db.load_column_layout()
        names = [c[0] for c in layout]
        col_name = result_column_name(rel.name)
        if col_name in names:
            raise ProjectError(f"A column named '{col_name}' already exists.")

        new_layout = list(layout)
        new_layout.append((col_name, "ReleaseResultColumn", True, 120))
        if not any(c[1] == "Last Result" for c in layout):
            new_layout.append(("Last Result", "Last Result", True, 110))
        db.save_column_layout(new_layout)

        bindings[col_name] = release_id
        db.set_meta(RESULT_BINDINGS_KEY, json.dumps(bindings))
        db.commit()
        bus.publish("db-changed", {"reason": "result-column-added", "release_id": release_id})
        return {"name": col_name, "release_id": release_id}
    return _guard(go)


@router.post("/{release_id}/unfreeze")
def unfreeze_release(release_id: int, state: AppState = Depends(get_state),
                     bus: EventBus = Depends(get_bus)) -> dict:
    """Convert a baseline back into an editable release (inverse of Freeze)."""
    def go():
        state.require_edit()
        rm = state.require_releases()
        idx = state.release_index_by_id(release_id)
        try:
            r = rm.unfreeze_baseline(idx)
        except ValueError as e:
            raise ProjectError(str(e)) from e
        bus.publish("db-changed", {"reason": "release-unfrozen", "release_id": release_id})
        return {"id": r.id, "name": r.name, "is_baseline": r.is_baseline}
    return _guard(go)


@router.post("/{release_id}/source")
def import_release_source(release_id: int, body: ImportSourceBody,
                          state: AppState = Depends(get_state),
                          jobs: JobManager = Depends(get_jobs)) -> dict:
    """#2E: import C/H source from a local folder into the DB for this release.

    Runs as the ``import_source`` background job (gzip-compressing each file on a
    worker thread); returns the job snapshot so the client can track progress.
    The job publishes ``db-changed`` on completion → the ✓ Source badge updates.
    """
    def go():
        state.require_edit()
        if not body.source_dir:
            raise ProjectError("source_dir is required.")
        job = jobs.start("import_source",
                         {"release_id": release_id, "source_dir": body.source_dir})
        return job.public()
    return _guard(go)


# ---------------------------------------------------------------------------
# Compare/previous release — the release to diff/ground against (the "previous
# branch revision"). Shared by the Change Log and AI Generation so both default
# to, and remember, the same selection. Stored in ui_state.
# ---------------------------------------------------------------------------
COMPARE_UI_KEY = "compare_previous_release_id"


class CompareReleaseBody(BaseModel):
    previous_release_id: Optional[int] = None


def _default_previous_release_id(rm) -> Optional[int]:
    """The active release's lineage parent (the revision it was branched from);
    falls back to the most recent other selectable release."""
    active = rm.get_active_release()
    selectable = [r for r in rm.releases if not r.is_baseline and not r.is_deleted]
    if active is not None and active.parent_release_name:
        for r in selectable:
            if r.name == active.parent_release_name:
                return r.id
    others = [r for r in selectable if active is None or r.id != active.id]
    return others[0].id if others else None


@router.get("/compare")
def get_compare_release(state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        rm = state.require_releases()
        default_id = _default_previous_release_id(rm)
        raw = db.get_ui_state(COMPARE_UI_KEY)
        chosen = None
        if raw is not None:
            try:
                chosen = int(raw)
            except (TypeError, ValueError):
                chosen = None
        # Drop a stale stored id (release deleted) → fall back to the default.
        valid_ids = {r.id for r in rm.releases if not r.is_baseline and not r.is_deleted}
        if chosen not in valid_ids:
            chosen = default_id
        return {"previous_release_id": chosen, "default_previous_release_id": default_id}
    return _guard(go)


@router.put("/compare")
def set_compare_release(body: CompareReleaseBody,
                        state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        db.set_ui_state(COMPARE_UI_KEY,
                        None if body.previous_release_id is None
                        else str(body.previous_release_id))
        return {"previous_release_id": body.previous_release_id}
    return _guard(go)


@router.delete("/{release_id}/source")
def drop_release_source(release_id: int, state: AppState = Depends(get_state),
                        bus: EventBus = Depends(get_bus)) -> dict:
    """#2E: drop ONLY the stored source blobs for a release (mind/code maps stay).

    Frees database file space at the cost of code-map source viewing and test
    injection for this release until source is re-imported.
    """
    def go():
        db = state.require_edit()
        db.delete_release_source(release_id)
        db.commit()
        bus.publish("db-changed",
                    {"reason": "source-dropped", "release_id": release_id})
        return {"release_id": release_id, "result": "source dropped"}
    return _guard(go)

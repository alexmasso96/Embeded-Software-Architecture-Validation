"""
Job handlers (plan §3.1). Each adapts a pure ``Logic_*`` job function to the
``(params, progress, cancel_event) -> result`` contract and is registered with
the JobManager under its kind.

The pure jobs already take a ``progress_cb`` and (where relevant) open their own
SQLite connection on the worker thread — that own-connection rule is what keeps
a build crash-free while the main connection is busy (see build_code_map_job /
run_release_diff). Handlers therefore stay thin.
"""
from __future__ import annotations

import json
import math
import threading
import time
from contextlib import contextmanager
from typing import Callable

from Application_Logic.Logic_Change_Log_Tab import run_release_diff
from Application_Logic.Logic_Code_Map_Tab import build_code_map_job

from .jobs import JobManager
from .state import AppState, ProjectError


def register_handlers(jobs: JobManager, state: AppState) -> None:
    jobs.register("_demo", _demo_handler)
    jobs.register("release_diff", _make_release_diff(state))
    jobs.register("build_code_map", _make_build_code_map(state))
    jobs.register("fuzzy_rematch", _make_fuzzy_rematch(state))
    jobs.register("build_mind_map", _make_build_mind_map(state))
    jobs.register("generate_tests", _make_generate_tests(state))
    jobs.register("parse_elf", _make_parse_elf(state))
    jobs.register("import_symbols", _make_import_symbols(state))
    jobs.register("import_source", _make_import_source(state))


# ----------------------------------------------------------------------
# Shared: a worker-thread-owned DB connection to the open project (the
# crash-safe pattern — never write the main connection from a job thread).
# ----------------------------------------------------------------------
@contextmanager
def _worker_db(state: AppState):
    from Application_Logic.Logic_Database import ProjectDatabase
    main = state.require_open()
    wdb = ProjectDatabase()
    wdb.open(main.db_path, create_schema=False, apply_journal=False)
    wdb.set_block_cipher(state.block_cipher())
    try:
        yield wdb
    finally:
        try:
            wdb.close()
        except Exception:  # noqa: BLE001
            pass


def _resolve_model_ids(state: AppState, params: dict, wdb) -> list[int]:
    ids = params.get("model_ids")
    if ids:
        return list(ids)
    mid = state.require_arch().active_model_id
    if mid is None:
        raise ProjectError("No active model and no model_ids given.")
    return [mid]


def _extract_ports(wdb, layout, model_id: int) -> list[dict]:
    """[{name, operation}] from a model's rows, deduped — headless port pull
    (the Qt _extract_ports). Port col = first 'Port Search'; ops col from meta."""
    port_col = next((c[0] for c in layout if c[1] == "Port Search"), None)
    ops_col = wdb.get_meta("operations_column_name")
    ports, seen = [], set()
    for r in wdb.get_model_rows(model_id):
        name = (r.get(port_col, {}) or {}).get("text", "").strip() if port_col else ""
        op = (r.get(ops_col, {}) or {}).get("text", "").strip() if ops_col else ""
        if not name:
            continue
        key = (name, op)
        if key in seen:
            continue
        seen.add(key)
        ports.append({"name": name, "operation": op})
    return ports


# ----------------------------------------------------------------------
# _demo — a dependency-free job for exercising the lifecycle/SSE/cancel path
# in tests without ELF or project fixtures.
# ----------------------------------------------------------------------
def _demo_handler(params: dict, progress: Callable[..., None],
                  cancel: threading.Event):
    steps = int(params.get("steps", 3))
    delay = float(params.get("delay", 0.0))
    # `burn` seconds of GIL-holding CPU work per step — used by the freeze probe
    # (scripts/freeze_probe.py) to load the worker process and prove the UI
    # process stays responsive across the process boundary.
    burn = float(params.get("burn", 0.0))
    done = 0
    for i in range(steps):
        if cancel.is_set():
            break
        done = i + 1
        progress(f"step {done}/{steps}", percent=100.0 * done / steps)
        if burn:
            end = time.monotonic() + burn
            x = 0.0
            while time.monotonic() < end:
                for _ in range(20000):
                    x += math.sqrt(123.456)  # CPU, holds the GIL
                if cancel.is_set():
                    break
        elif delay:
            time.sleep(delay)
    return {"steps_completed": done, "echo": params.get("echo")}


# ----------------------------------------------------------------------
def _make_release_diff(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        db = state.require_open()
        cur = params.get("current_release_id")
        prev = params.get("previous_release_id")
        if cur is None or prev is None:
            raise ProjectError("current_release_id and previous_release_id are required.")
        model_id = params.get("model_id")
        if model_id is None:
            model_id = state.require_arch().active_model_id
        if model_id is None:
            raise ProjectError("model_id is required (no active model).")

        progress("Computing release diff…")
        diff_hash, diffs = run_release_diff(db.db_path, cur, prev,
                                            cipher=state.block_cipher())

        # Persist on the worker's OWN connection (the crash-safe pattern: the
        # main connection stays untouched from this thread). The Change Log then
        # reads the rows back through the main connection.
        progress("Saving diffs…")
        from Application_Logic.Logic_Database import ProjectDatabase
        wdb = ProjectDatabase()
        try:
            wdb.open(db.db_path, create_schema=False, apply_journal=False)
            wdb.set_block_cipher(state.block_cipher())
            wdb.save_code_diffs(model_id, diff_hash, diffs)
            wdb.set_model_diff_hash(model_id, diff_hash, release_id=cur)
            wdb.set_meta("ai_last_diff_hash", diff_hash)
            wdb.commit()
        finally:
            wdb.close()
        return {"diff_hash": diff_hash, "file_count": len(diffs), "model_id": model_id}
    return handler


# ----------------------------------------------------------------------
def _make_build_code_map(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        db = state.require_open()
        model_id = params.get("model_id")
        if model_id is None:
            raise ProjectError("model_id is required.")
        code_map = build_code_map_job(
            db.db_path,
            params.get("elf_hash"),
            params.get("elf_path"),
            params.get("source_dir"),
            model_id,
            params.get("release_id"),
            progress_cb=lambda msg: progress(msg),
            cipher=state.block_cipher(),
        )
        # The build may have imported source into the DB (an explicitly chosen
        # folder) — tell clients so the ✓ Source badge / Code Map source status
        # refresh without a manual reload.
        state.bus.publish("db-changed",
                          {"reason": "code-map-built",
                           "release_id": params.get("release_id")})
        return {"functions": len(code_map.get("functions", {}))}
    return handler


# ----------------------------------------------------------------------
# fuzzy_rematch — re-run symbol matching for a model's rows against the
# active release's ELF, writing "Name (NN%)" into each (Match) cell.
# ----------------------------------------------------------------------
def _make_fuzzy_rematch(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic.Logic_Symbol_Matcher import (
            SymbolMatcher, search_specs_from_layout, rematch_rows,
        )
        state.require_edit()
        elf_hash = params.get("elf_hash") or state.active_elf_hash()
        if not elf_hash:
            raise ProjectError("No ELF imported for the active release.")
        with _worker_db(state) as wdb:
            if not wdb.has_elf(elf_hash):
                raise ProjectError(f"No ELF in project for hash {elf_hash}.")
            matcher = SymbolMatcher(None, db=wdb, elf_hash=elf_hash)
            specs = search_specs_from_layout(wdb.load_column_layout())
            model_ids = _resolve_model_ids(state, params, wdb)
            total = 0
            for i, mid in enumerate(model_ids, 1):
                if cancel.is_set():
                    break
                progress(f"Re-matching model {i}/{len(model_ids)}…")
                rows = wdb.get_model_rows(mid)
                changed = rematch_rows(rows, specs, matcher)
                if changed:
                    wdb.save_model_rows(mid, rows)
                total += changed
            wdb.commit()
        return {"cells_changed": total, "models": len(model_ids)}
    return handler


# ----------------------------------------------------------------------
# build_mind_map — own-connection wrapper around run_mindmap_job (which takes
# a live db and writes through it).
# ----------------------------------------------------------------------
def _make_build_mind_map(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic.Logic_AI_Chat import run_mindmap_job
        from Application_Logic.Logic_AI_Context import META_REQUIREMENTS
        from Application_Logic.Logic_Source_Store import release_source_provider
        state.require_edit()
        with _worker_db(state) as wdb:
            current_rid = params.get("current_release_id")
            if current_rid is None:
                current_rid = wdb.get_active_release_id()
            if current_rid is None:
                raise ProjectError("No current release for the mind map.")
            previous_rid = params.get("previous_release_id")

            current_source = release_source_provider(wdb, current_rid)
            if current_source is None:
                raise ProjectError("The current release has no source imported.")
            previous_source = (release_source_provider(wdb, previous_rid)
                               if previous_rid is not None else None)

            raw_reqs = wdb.get_meta(META_REQUIREMENTS)
            try:
                reqs = json.loads(raw_reqs) if raw_reqs else []
            except (ValueError, TypeError):
                reqs = []

            layout = wdb.load_column_layout()
            names = {m["id"]: m["name"] for m in wdb.get_all_models()}
            model_ids = _resolve_model_ids(state, params, wdb)
            mm_jobs = [(mid, names.get(mid, str(mid)), _extract_ports(wdb, layout, mid), reqs)
                       for mid in model_ids]

            built = run_mindmap_job(mm_jobs, current_source, previous_source, wdb,
                                    release_id=current_rid, progress_cb=progress)
        return {"maps_built": built, "models": len(model_ids)}
    return handler


# ----------------------------------------------------------------------
# generate_tests — AI low-level test generation from an HLT design file.
# Network + writes <Model>_LowLevel.md.
# ----------------------------------------------------------------------
def _make_generate_tests(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic import Logic_AI_Context as ctx
        from Application_Logic.Logic_AI_Generation import run_generation_job
        from Application_Logic.Logic_Source_Store import release_source_provider
        state.require_open()
        project_path = state.project_path
        provider_id = params.get("provider_id")
        model = params.get("model")
        hlt_path = params.get("hlt_path")
        if not (provider_id and model and hlt_path):
            raise ProjectError("provider_id, model, and hlt_path are required.")

        parsed = ctx.parse_hlt_file(hlt_path)
        cases = parsed["test_cases"]
        wanted = params.get("test_case_ids")
        if wanted is not None:
            wanted = set(wanted)
            cases = [c for c in cases if c["id"] in wanted]
        if not cases:
            raise ProjectError("No test cases selected.")

        with _worker_db(state) as wdb:
            rules = ctx.get_rules(wdb)
            prompt = ctx.get_prompt(wdb)
            rid = params.get("current_release_id")
            if rid is None:
                rid = wdb.get_active_release_id()
            source = release_source_provider(wdb, rid) if rid is not None else None
            output_dir = ctx.hlt_output_dir(project_path)
            path = run_generation_job(
                provider_id, model, rules, prompt, source, output_dir,
                parsed["model_name"], parsed["title"], cases,
                progress_cb=progress,
                case_done_cb=lambda tc_id, _t: progress(f"Generated {tc_id}"),
                stop_check=cancel.is_set,
            )
        return {"output_path": path, "cases": len(cases)}
    return handler


# ----------------------------------------------------------------------
# parse_elf — import an ELF into a release: parse + stream symbols to the DB,
# then key the release to the new ELF hash.
# ----------------------------------------------------------------------
def _make_parse_elf(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic.Logic_New_Project import ElfImportTask
        state.require_edit()
        file_path = params.get("file_path")
        release_id = params.get("release_id")
        if not file_path or release_id is None:
            raise ProjectError("file_path and release_id are required.")

        with _worker_db(state) as wdb:
            progress("Parsing ELF…")
            task = ElfImportTask(project_db=wdb, db_path=None)
            parser = task.import_elf(file_path)
            elf_hash = getattr(parser, "md5_hash", None) or getattr(parser, "_active_elf_hash", None)
            wdb.update_release(release_id, elf_path=file_path, elf_hash=elf_hash)
            wdb.commit()
            fn_count = len(wdb.get_function_names(elf_hash)) if elf_hash else 0

        # Reflect the new ELF on the in-memory release so the symbols endpoint's
        # active_elf_hash() sees it without a reopen (a plain attribute set).
        if state.release_manager is not None:
            for r in state.release_manager.releases:
                if r.id == release_id:
                    r.elf_path = file_path
                    r.elf_hash = elf_hash
                    break
        state._matchers.pop(elf_hash, None)
        return {"elf_hash": elf_hash, "functions": fn_count, "release_id": release_id}
    return handler


# ----------------------------------------------------------------------
# import_source — import C/H source from a local folder into the DB, keyed to a
# release (#2E). Stored gzip-compressed so the source travels with the .arch and
# the code map / test injection can read it without the original tree present.
# ----------------------------------------------------------------------
def _make_import_source(state: AppState):
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic.Logic_Source_Store import FilesystemSourceProvider
        state.require_edit()
        release_id = params.get("release_id")
        source_dir = params.get("source_dir")
        if release_id is None or not source_dir:
            raise ProjectError("release_id and source_dir are required.")

        with _worker_db(state) as wdb:
            progress("Scanning source folder…")
            # save_release_source_files calls progress(rel_path, idx, total_or_None)
            # per file — surface it as the job's per-file message (total is None,
            # so the bar stays indeterminate).
            count = wdb.save_release_source_files(
                release_id,
                FilesystemSourceProvider(source_dir).iter_text(),
                progress=lambda rel_path, idx, _total: progress(
                    f"Importing {rel_path}"),
            )
            wdb.commit()

        # Tell every client the source set changed so the Release Manager's
        # ✓ Source badge + the workspace refresh without a manual reload.
        state.bus.publish("db-changed",
                          {"reason": "source-imported", "release_id": release_id})
        return {"files": count, "release_id": release_id}
    return handler


def _detect_import_kind(file_path: str) -> str:
    """'elf' or 'json' from the file — magic bytes first, then extension.

    The new-project Import flow is type-agnostic: the UI hands us a file and we
    pick the right importer (ELF binary vs exported JSON symbol cache).
    """
    import os
    try:
        with open(file_path, "rb") as f:
            magic = f.read(4)
    except OSError as e:
        raise ProjectError(f"Cannot read import file: {e}") from e
    if magic[:4] == b"\x7fELF":
        return "elf"
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".json":
        return "json"
    if ext == ".elf":
        return "elf"
    raise ProjectError("Unsupported import file — expected an .elf binary or a .json symbol cache.")


def _make_import_symbols(state: AppState):
    """Auto-detecting symbol import (the new-project 'Import' option). Detects
    ELF vs JSON and dispatches to the matching ElfImportTask path, then keys the
    given release to the imported ELF hash. Mirrors parse_elf but type-agnostic."""
    def handler(params: dict, progress: Callable[..., None], cancel: threading.Event):
        from Application_Logic.Logic_New_Project import ElfImportTask
        state.require_edit()
        file_path = params.get("file_path")
        release_id = params.get("release_id")
        if not file_path or release_id is None:
            raise ProjectError("file_path and release_id are required.")
        kind = _detect_import_kind(file_path)

        with _worker_db(state) as wdb:
            task = ElfImportTask(project_db=wdb, db_path=None)
            if kind == "elf":
                progress("Parsing ELF…")
                parser = task.import_elf(file_path)
            else:
                progress("Loading symbol cache…")
                parser = task.import_json(file_path)
            elf_hash = getattr(parser, "md5_hash", None) or getattr(parser, "_active_elf_hash", None)
            wdb.update_release(release_id, elf_path=file_path, elf_hash=elf_hash)
            wdb.commit()
            fn_count = len(wdb.get_function_names(elf_hash)) if elf_hash else 0

        if state.release_manager is not None:
            for r in state.release_manager.releases:
                if r.id == release_id:
                    r.elf_path = file_path
                    r.elf_hash = elf_hash
                    break
        state._matchers.pop(elf_hash, None)
        return {"kind": kind, "elf_hash": elf_hash, "functions": fn_count,
                "release_id": release_id}
    return handler

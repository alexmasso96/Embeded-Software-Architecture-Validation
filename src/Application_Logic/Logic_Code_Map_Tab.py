"""
Code Map — build job, call-graph traversal, and symbol lookup (pure logic).

Phase 0 (pywebview migration): Qt-free. The Qt tab controller lives in
UI/tab_code_map.py and calls into these functions; after Phase 1 the FastAPI
`codemap` router does the same (`build_code_map_job` becomes the
`build_code_map` job kind, `compute_graph_levels` feeds the graph endpoint).
"""
import html
import logging
import os
from collections import deque

logger = logging.getLogger(__name__)

MAX_GRAPH_NODES = 60


def build_code_map_job(db_path, elf_hash, elf_path, source_dir, model_id,
                       release_id=None, progress_cb=lambda msg: None, cipher=None):
    """Builds the C source index + joined code map. Run me on a worker thread.

    Crash-safety: uses its OWN SQLite connection (not the app's shared one).
    Using a single connection from two threads is what crashes today when an
    import / model-move runs during a build. Two separate connections never
    crash — at worst they briefly contend on the file lock (handled by
    busy_timeout), and that is WAL-independent (works in DELETE mode on network
    drives too). The finished map is also written + committed on this own
    connection, so the result is durable the moment the build finishes —
    independent of any project Save.

    Returns the code_map dict; raises on failure.
    """
    import json
    from pathlib import Path
    from Application_Logic.Logic_Database import ProjectDatabase
    from core.elf_parser import ELFParser

    wdb = ProjectDatabase()
    try:
        # Own connection to the same .arch (lightweight: no journal/schema redo).
        wdb.open(db_path, create_schema=False, apply_journal=False)
        # Attach the session cipher so DB-stored source / maps decrypt + re-encrypt.
        wdb.set_block_cipher(cipher)

        # Worker-side parser bound to the worker's own connection (DB-backed
        # DWARF reads) + the ELF path (Capstone reads function bytes from disk).
        wparser = ELFParser()
        wparser.elf_path = Path(elf_path) if elf_path else None
        wparser._db = wdb
        wparser._active_elf_hash = elf_hash

        from Application_Logic.Logic_Code_Map import build_code_map, elf_has_call_tree

        # 2B/2C: probe whether the ELF actually yields a usable call tree
        # (disassembly recovers real edges). A bare elf_functions row count
        # isn't enough — a relocatable/ET_REL or stripped ELF has symbols but
        # no disassemblable call edges. When there's no usable tree we route
        # to the source-derived call graph as the primary edges (#2C).
        has_call_tree = (bool(elf_path) and os.path.exists(elf_path)
                         and elf_has_call_tree(wparser))
        if has_call_tree:
            progress_cb("ELF call tree available — joining symbols + disassembly.")
        else:
            progress_cb("No ELF call tree available — building the call graph "
                        "from the source code.")

        code_index = None
        from Application_Logic.Logic_Code_Index import build_index
        # #2E: an explicitly chosen source folder is imported + linked to the
        # release (replacing any previously stored source) so the source travels
        # inside the .arch. After this the release HAS source, so we always index
        # from the DB below (WAL-independent, on the worker's OWN connection).
        # The Code Map UI passes an empty source_dir for a plain "build from the
        # already-imported source", which skips this and indexes the DB directly.
        if (release_id is not None and source_dir and os.path.exists(source_dir)):
            progress_cb("Importing release source into the database…")
            from Application_Logic.Logic_Source_Store import FilesystemSourceProvider
            wdb.save_release_source_files(
                release_id, FilesystemSourceProvider(source_dir).iter_text())

        # #2E: prefer source stored in the DB for this release (read on the
        # worker's OWN connection — WAL-independent); else a linked local folder.
        if (release_id is not None and wdb.has_release_source(release_id)):
            progress_cb("Indexing release source from the database…")
            from Application_Logic.Logic_Source_Store import DbReleaseSourceProvider
            code_index = build_index(DbReleaseSourceProvider(wdb, release_id))
        elif source_dir and os.path.exists(source_dir):
            progress_cb("Indexing source files…")
            code_index = build_index(source_dir)

        # #2C: with no ELF call tree AND no source, the graph can only be a bare
        # symbol list — tell the user how to get real edges instead.
        if not has_call_tree and code_index is None:
            progress_cb("⚠ No ELF call tree and no source linked — the call "
                        "graph will have no edges. Map/Import source for this "
                        "release (or link a local folder) to build it from source.")

        progress_cb("Building code map (call graph & symbol join)…")
        # Pass the probe result so build_code_map doesn't re-disassemble to decide.
        code_map = build_code_map(wparser, code_index, source_root=source_dir or "",
                                  prefer_source_calls=not has_call_tree)

        # Commit on the worker's own connection → durable immediately, no project
        # Save required, nothing lost if the user doesn't hit Save afterwards.
        progress_cb("Saving code map…")
        if model_id is not None:
            wdb.save_model_code_map(model_id, json.dumps(code_map),
                                    release_id=release_id)
            wdb.set_meta("code_map_index_state", "done")
            wdb.commit()
        return code_map
    finally:
        try:
            wdb.close()
        except Exception:
            pass


def build_callers_map(functions):
    """Inverts the per-function ``calls`` lists into {callee -> set(callers)}."""
    callers_map = {fName: set() for fName in functions}
    for fName, fData in functions.items():
        for target in fData.get("calls", []):
            if target not in callers_map:
                callers_map[target] = set()
            callers_map[target].add(fName)
    return callers_map


def is_known_function(dataset, word):
    """True if `word` is a function in the loaded code map."""
    return (bool(word) and bool(dataset)
            and word in dataset.get("functions", {}))


def describe_symbol(dataset, word):
    """Classify `word` against the loaded code map and return an HTML tooltip
    string, or None if it isn't a known symbol. Dynamic text is HTML-escaped."""
    if not word or not dataset:
        return None
    funcs = dataset.get("functions", {})
    if word in funcs:
        f = funcs[word]
        sig = html.escape(f.get("signature") or f"{word}()")
        ret = html.escape(f.get("return_type") or "void")
        file = f.get("file") or ""
        line = f.get("line_start", 0)
        loc = html.escape(f"{file}:{line}" if file else "location unknown")
        return (f"<b>{sig}</b><br/>"
                f"<i>function</i> · returns <code>{ret}</code><br/>{loc}")
    gvars = dataset.get("global_variables", {})
    if word in gvars:
        return (f"<b>{html.escape(word)}</b><br/><i>global variable</i> · "
                f"<code>{html.escape(str(gvars[word]))}</code>")
    defines = dataset.get("defines", {})
    if word in defines:
        val = defines[word]
        val_str = f" {html.escape(str(val))}" if val not in (None, "") else ""
        return f"<code>#define {html.escape(word)}{val_str}</code>"
    return None


def extract_function_block_by_line(content, line_start):
    """Extracts one function body from `content` by brace matching, starting at
    `line_start` (1-based). Falls back to 100 lines when braces never balance."""
    lines = content.splitlines()
    start_line_idx = max(0, line_start - 1)
    sub_content = "\n".join(lines[start_line_idx:])

    brace_count = 0
    in_braces = False

    for idx, char in enumerate(sub_content):
        if char == '{':
            brace_count += 1
            in_braces = True
        elif char == '}':
            brace_count -= 1

        if in_braces and brace_count == 0:
            return sub_content[:idx+1]

    return "\n".join(lines[start_line_idx:start_line_idx+100])


def compute_graph_levels(dataset, callers_map, focused_func, back_depth,
                         forward_depth, max_nodes=MAX_GRAPH_NODES):
    """BFS around `focused_func`: callees forward, callers backward.

    Returns ``(level_nodes, node_levels, total_nodes)`` where ``level_nodes``
    maps level → [function names] (level 0 = focus, negative = callers,
    positive = callees) and ``total_nodes`` is the count BEFORE truncation —
    when it exceeds ``max_nodes`` the returned dicts are already pruned, so
    callers compare ``total_nodes > max_nodes`` to know a warning is due.
    """
    level_nodes = {0: [focused_func]}
    node_levels = {focused_func: 0}

    # Forward BFS (callees)
    queue = deque([(focused_func, 0)])
    while queue:
        node, d = queue.popleft()
        if d >= forward_depth:
            continue

        callees = dataset["functions"].get(node, {}).get("calls", [])
        for c in callees:
            if c not in node_levels:
                node_levels[c] = d + 1
                if (d + 1) not in level_nodes:
                    level_nodes[d + 1] = []
                level_nodes[d + 1].append(c)
                queue.append((c, d + 1))

    # Backward BFS (callers)
    queue = deque([(focused_func, 0)])
    while queue:
        node, d = queue.popleft()
        if d >= back_depth:
            continue

        callers = callers_map.get(node, [])
        for c in callers:
            if c not in node_levels:
                lvl = -(d + 1)
                node_levels[c] = lvl
                if lvl not in level_nodes:
                    level_nodes[lvl] = []
                level_nodes[lvl].append(c)
                queue.append((c, d + 1))

    # Node count limit + mitigation: prune to max_nodes, keeping the focus.
    total_nodes = len(node_levels)
    if total_nodes > max_nodes:
        nodes_kept = {focused_func}
        count = 1

        all_other_nodes = [n for n in node_levels if n != focused_func]
        for n in all_other_nodes:
            if count >= max_nodes:
                break
            nodes_kept.add(n)
            count += 1

        for lvl in list(level_nodes.keys()):
            level_nodes[lvl] = [n for n in level_nodes[lvl] if n in nodes_kept]
            if not level_nodes[lvl]:
                del level_nodes[lvl]

        node_levels = {n: lvl for n, lvl in node_levels.items() if n in nodes_kept}

    return level_nodes, node_levels, total_nodes

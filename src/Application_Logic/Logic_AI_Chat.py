"""
Advanced AI Chat — mind-map / chat jobs and markdown rendering (pure logic).

Phase 0 (pywebview migration): Qt-free. The Qt tab controller lives in
UI/tab_ai_chat.py and runs these jobs on worker threads; after Phase 1 the
FastAPI job manager runs `run_mindmap_job` as the `build_mind_map` job and
the `ai` router streams `run_chat_job`. The heavy logic lives in
Logic_AI_Context / Logic_AI_Providers / Logic_AI_Tools (unit-tested).
"""
import datetime
import json
import logging
import os

from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Context as ctx

logger = logging.getLogger(__name__)

_META_LAST_DIFF = "ai_last_diff_hash"

import re as _re
import html as _html


def _md_inline(s: str) -> str:
    """Inline markdown → HTML: `code`, **bold**, *italic*. HTML-escaped first."""
    codes = []
    s = _re.sub(r"`([^`]+)`", lambda m: codes.append(m.group(1)) or f"\x01{len(codes)-1}\x01", s)
    s = _html.escape(s)
    s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = _re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    s = _re.sub(r"(?<![\*\w])\*([^*]+?)\*(?![\*\w])", r"<i>\1</i>", s)
    for i, c in enumerate(codes):
        s = s.replace(f"\x01{i}\x01",
                      f"<code style='background-color:#1b1b1b;'>{_html.escape(c)}</code>")
    return s


def md_to_html(md: str) -> str:
    """Minimal, dependency-free markdown → Qt-rich-text HTML for AI chat bubbles.
    Handles fenced code blocks, headings, bold/italic, inline code, and bullet/
    numbered lists. Output inherits the bubble's (light) text colour."""
    md = md or ""
    code_blocks = []
    md = _re.sub(r"```[^\n]*\n?(.*?)```",
                 lambda m: code_blocks.append(m.group(1).rstrip("\n")) or f"\x00C{len(code_blocks)-1}\x00",
                 md, flags=_re.S)
    out, list_mode = [], None
    for raw in md.split("\n"):
        ul = _re.match(r"^\s*[-*+]\s+(.*)$", raw)
        ol = _re.match(r"^\s*\d+\.\s+(.*)$", raw)
        if ul or ol:
            kind = "ul" if ul else "ol"
            if list_mode != kind:
                if list_mode:
                    out.append(f"</{list_mode}>")
                out.append(f"<{kind}>")
                list_mode = kind
            out.append(f"<li>{_md_inline((ul or ol).group(1))}</li>")
            continue
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None
        h = _re.match(r"^\s*#{1,6}\s+(.*)$", raw)
        if h:
            out.append(f"<b>{_md_inline(h.group(1))}</b><br>")
        elif raw.strip() == "":
            out.append("<br>")
        else:
            out.append(_md_inline(raw) + "<br>")
    if list_mode:
        out.append(f"</{list_mode}>")
    res = "".join(out)
    for i, b in enumerate(code_blocks):
        res = res.replace(
            f"\x00C{i}\x00",
            f"<pre style='background-color:#1b1b1b; padding:6px;'>{_html.escape(b)}</pre>")
    return res


def run_mindmap_job(jobs, current_source, previous_source, db, release_id=None,
                    progress_cb=lambda msg: None):
    """Builds mind maps (and code-map joins / diffs as needed) for each job.
    Run me on a worker thread.

    ``jobs`` is a list of (model_id, model_name, ports, requirements) tuples;
    ``release_id`` pins the maps to that release (#2E). Returns the number of
    maps built; raises on failure.
    """
    diff_hash = ""
    diffs = None
    if previous_source and current_source:
        diff_hash = ctx.compute_diff_hash(current_source, previous_source)
        db.set_meta(_META_LAST_DIFF, diff_hash)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    # #2E: use the ELF of the SELECTED current release (release_id) so
    # the code map matches the source being indexed; fall back to the active
    # release when no specific release was pinned.
    active_elf_hash = None
    active_elf_path = None
    releases = db.get_all_releases()
    for r in releases:
        if r.get("is_deleted", 0) or not r.get("elf_hash"):
            continue
        match = (r.get("id") == release_id if release_id is not None
                 else r.get("is_active", 0) == 1)
        if match:
            active_elf_hash = r["elf_hash"]
            active_elf_path = r["elf_path"]
            break

    for (mid, name, ports, reqs) in jobs:
        progress_cb(f"Indexing model '{name}' …")

        # Check if we should build the CodeMap
        code_map = None
        code_map_json = None
        if active_elf_hash:
            # Check if CodeMap is already pregenerated in the DB
            pregenerated_code_map = db.get_model_code_map(mid, release_id=release_id)
            if pregenerated_code_map:
                progress_cb("Using pregenerated CodeMap call-graph from database …")
                code_map = pregenerated_code_map
                code_map_json = json.dumps(code_map)
            elif active_elf_path and os.path.exists(active_elf_path):
                progress_cb(f"Building CodeMap call-graph join for '{name}' …")
                try:
                    from core.elf_parser import ELFParser
                    from Application_Logic.Logic_Code_Index import build_index
                    from Application_Logic.Logic_Code_Map import build_code_map

                    # Set up the parser backed by our DB
                    parser = ELFParser(active_elf_path)
                    parser.load_elf(active_elf_path)
                    parser.extract_all_streaming_to_db(db)

                    # Re-open or use the parser in database-backed mode
                    parser = ELFParser(active_elf_path)
                    parser._db = db
                    parser._active_elf_hash = active_elf_hash

                    # Build static C AST index
                    code_index = build_index(current_source) if current_source else None

                    # Build Joined CodeMap
                    code_map = build_code_map(parser, code_index, source_root=current_source or "")
                    code_map_json = json.dumps(code_map)
                except Exception as e:
                    progress_cb(f"Warning: Failed to build CodeMap: {e}")
                    logger.warning(f"Failed to build CodeMap: {e}")

        model_diffs = []
        if diff_hash:
            # Check if DB has diffs for this model and hash
            cur = db._conn.execute(
                "SELECT 1 FROM ai_code_diffs WHERE model_id=? AND diff_hash=? LIMIT 1",
                (mid, diff_hash)
            )
            if cur.fetchone():
                progress_cb(f"Using pregenerated diffs for model '{name}' …")
                model_diffs = db.get_code_diffs(mid, diff_hash)
            else:
                if diffs is None:
                    progress_cb("Computing file-by-file diffs (this reads changed files)…")
                    diffs = ctx.diff_source_folders(current_source, previous_source)
                model_diffs = diffs

        mm = ctx.build_mind_map(current_source, name, mid, ports, reqs,
                                generated_at=now, code_map=code_map)
        db.save_model_mindmap(
            mid, json.dumps(mm), source_hash=mm.get("source_hash", ""),
            diff_hash=diff_hash, builder_version=mm.get("builder_version", ""),
            char_count=ctx.mind_map_char_count(mm), updated_at=now,
            code_map_json=code_map_json, release_id=release_id)
        if diff_hash and model_diffs:
            db.save_code_diffs(mid, diff_hash, model_diffs)
    db.commit()
    return len(jobs)


def run_chat_job(provider_id, model, messages, tools, executor, system_prompt,
                 on_tool_call=lambda name, args: None, stop_check=lambda: False):
    """One agentic chat turn (tool loop included). Run me on a worker thread.
    Returns the assistant's final text; raises on failure (incl. AIStopped)."""
    return providers.generate_with_tools(
        provider_id, model, messages, tools,
        tool_executor=executor, system_prompt=system_prompt,
        on_tool_call=on_tool_call, stop_check=stop_check)

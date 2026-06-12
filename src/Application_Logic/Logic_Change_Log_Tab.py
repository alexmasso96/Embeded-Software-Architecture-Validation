"""
Change Log — diff engine and AI change-log generation (pure logic).

Phase 0 (pywebview migration): Qt-free. The Qt tab controller lives in
UI/tab_change_log.py and calls into these functions; after Phase 1 the
FastAPI `changelog` router does the same.
"""
import logging

logger = logging.getLogger(__name__)

MAX_PROMPT_DIFF_LEN = 15000

GENERATE_BUTTON_LABEL = "Generate AI Change Log (requires AI Token)"


def parse_and_align_diff(diff_text: str):
    """Parses a unified diff string and aligns the old and new code side-by-side.

    Returns lists of tuples (line_content, line_type) for the old and new views.
    """
    if not diff_text or diff_text.strip().startswith("(diff omitted") or diff_text.strip().startswith("(diff truncated"):
        return [(diff_text, "header")], [(diff_text, "header")]

    lines = diff_text.splitlines()
    old_aligned = []
    new_aligned = []

    i = 0
    n = len(lines)

    deletes = []
    adds = []

    def flush_deletes_adds():
        m = max(len(deletes), len(adds))
        for idx in range(m):
            del_line = deletes[idx] if idx < len(deletes) else None
            add_line = adds[idx] if idx < len(adds) else None

            if del_line is not None and add_line is not None:
                old_aligned.append((del_line, "deleted"))
                new_aligned.append((add_line, "added"))
            elif del_line is not None:
                old_aligned.append((del_line, "deleted"))
                new_aligned.append(("", "empty"))
            elif add_line is not None:
                old_aligned.append(("", "empty"))
                new_aligned.append((add_line, "added"))
        deletes.clear()
        adds.clear()

    while i < n:
        line = lines[i]
        if line.startswith('---') or line.startswith('+++') or line.startswith('index '):
            flush_deletes_adds()
            old_aligned.append((line, "header"))
            new_aligned.append((line, "header"))
            i += 1
        elif line.startswith('@@'):
            flush_deletes_adds()
            old_aligned.append((line, "header"))
            new_aligned.append((line, "header"))
            i += 1
        elif line.startswith('-'):
            deletes.append(line[1:])
            i += 1
        elif line.startswith('+'):
            adds.append(line[1:])
            i += 1
        elif line.startswith(' '):
            flush_deletes_adds()
            old_aligned.append((line[1:], "unchanged"))
            new_aligned.append((line[1:], "unchanged"))
            i += 1
        else:
            flush_deletes_adds()
            old_aligned.append((line, "unchanged"))
            new_aligned.append((line, "unchanged"))
            i += 1

    flush_deletes_adds()
    return old_aligned, new_aligned


def run_release_diff(db_path, cur_rid, prev_rid):
    """Diff two releases' DB-stored source trees. Runs on a worker thread —
    opens its own (WAL-independent) connection. Returns (diff_hash, diffs)."""
    from Application_Logic.Logic_Database import ProjectDatabase
    from Application_Logic.Logic_Source_Store import DbReleaseSourceProvider
    from Application_Logic.Logic_AI_Context import diff_source_folders, compute_diff_hash
    wdb = ProjectDatabase()
    try:
        wdb.open(db_path, create_schema=False, apply_journal=False)
        cur_p = DbReleaseSourceProvider(wdb, cur_rid)
        prev_p = DbReleaseSourceProvider(wdb, prev_rid)
        diff_hash = compute_diff_hash(cur_p, prev_p)
        diffs = diff_source_folders(cur_p, prev_p)
        return diff_hash, diffs
    finally:
        try:
            wdb.close()
        except Exception:
            pass


def build_changelog_prompt(diffs, active_model_name, max_diff_len=MAX_PROMPT_DIFF_LEN):
    """Builds the LLM prompt for the AI change log from computed diffs,
    truncating the combined unified-diff content at ``max_diff_len``."""
    diff_texts = []
    total_len = 0

    for d in diffs:
        header = f"\n--- File: {d['file_path']} ({d['status']}) ---\n"
        content = d["unified_diff"]
        if total_len + len(header) + len(content) > max_diff_len:
            diff_texts.append(header + "(unified diff content truncated for token limits...)")
            break
        diff_texts.append(header + content)
        total_len += len(header) + len(content)

    diffs_combined = "".join(diff_texts)

    return (
        f"Analyze the following software source code differences for the architecture model '{active_model_name}'.\n"
        f"Generate a professional, structured software change log suited for automotive/embedded standards (e.g. ASPICE, ISO 26262).\n"
        f"Summarize what was added, modified, or deleted, highlighting potential side-effects, safety-critical function changes, "
        f"and interface impacts.\n\n"
        f"--- Code Differences ---\n"
        f"{diffs_combined}"
    )


def generate_ai_changelog(provider_id, model, prompt):
    """Generates the AI change log synchronously (call from a worker thread).
    Returns the response text; raises on provider failure."""
    from Application_Logic import Logic_AI_Providers as providers

    # NB: providers' `Message` is a type alias (Dict[str, str]), NOT a class —
    # calling Message(...) raised "Type Dict cannot be instantiated". Messages
    # are plain dicts.
    messages = [
        {"role": "system", "content": "You are a senior software engineer and ASPICE auditor."},
        {"role": "user", "content": prompt},
    ]
    return providers.generate(provider_id, model, messages)

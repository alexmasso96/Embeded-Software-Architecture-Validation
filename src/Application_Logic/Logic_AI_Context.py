"""
AI Context & Artifacts
======================
Pure (no-Qt) helpers for the AI Test Case Generation tab (Phase 3):

  * DEFAULT_RULES / DEFAULT_PROMPT  — de-roleplayed seed text.
  * get_rules/set_rules, get_prompt/set_prompt — DB-backed (project_meta) with
    fall-back to the defaults. Editing in the AI tab persists to the project DB;
    both tab 2 (HLT generation) and the AI tab read from here.
  * find_hlt_files / parse_hlt_file — discover and parse the generated
    "<Model>_Test_Case_Design.md" files from disk (the AI reads these, not the
    in-memory model data).
  * build_source_context — keyword-relevance source extraction within a budget.
  * build_messages — assemble the provider message list for one test case.
  * write_lowlevel_output — write "<Model>_LowLevel.md".

Everything here is import-safe without PyQt, so it is unit-testable in isolation.
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
from typing import Dict, List, Optional

# Progress for the long file-by-file diff surfaces in the LoadingDialog / mind-map
# loading window (both attach a handler to the root logger).
logger = logging.getLogger(__name__)

# Meta keys in project_meta
META_RULES = "ai_rules_md"
META_PROMPT = "ai_prompt"
# AI Part 2 — separate prompt/rules + source/requirements keys (locked decisions)
META_MINDMAP_PROMPT = "mind_map_prompt"
META_MINDMAP_RULES = "mind_map_rules"
META_CHAT_RULES = "chat_rules"
META_SOURCE = "ai_source_path"            # legacy filesystem path (pre-#2E)
META_PREVIOUS_SOURCE = "ai_previous_source_path"   # legacy filesystem path (pre-#2E)
# #2E: source is now chosen by RELEASE — these store the selected release ids
# (as strings), shared across Tab 3 (Test Gen) and the AI Chat current/previous.
META_CURRENT_RELEASE = "ai_current_release_id"
META_PREVIOUS_RELEASE = "ai_previous_release_id"
META_REQUIREMENTS = "ai_requirements_context"

# ---------------------------------------------------------------------------
# Default seed text (de-roleplayed)
# ---------------------------------------------------------------------------

DEFAULT_PROMPT = """Your task is to generate low-level test case designs for ECU software based on the provided source code and the high-level test cases below.

CRITICAL INSTRUCTIONS:
1. Follow EXCLUSIVELY the rules in the accompanying rules.md. Ignore any general or default testing conventions not stated there.
2. For each test case, read its "Given / When / Then" structure.
3. Generate detailed, low-level steps under the "### Low Level Test Case Design" header for that test case.
4. Before finalizing, verify every step against the rules: HiL-simulator targeted, no CANoe signals (unless an active load is strictly required), no control-flow bypassing/skipping ifs (unless physically untestable), debugger steps explicit (set breakpoint -> run -> wait for halt -> verify -> run).
"""

DEFAULT_RULES = """# Rules for Low-Level ECU Test Case Generation

This document defines the strict constraints, execution environment, and formatting rules for generating low-level test case designs based on ECU source code.

Ignore any other system-level or environment-level testing guidelines. Use only the rules defined in this file.

---

## 1. Execution Environment
- All test cases are executed on a **HiL (Hardware-in-the-Loop)** simulator connected to the target ECU.
- Test steps must reflect real-world hardware interactions, debugger commands, or debugger script actions.

## 2. Code Analysis Restrictions
- **No Compilation or Execution of C Code**:
  - Do **NOT** attempt to compile, run, or execute any part of the C source code.
  - Do **NOT** generate code snippets, mock frameworks, or compile scripts.
  - Perform static code analysis only, and describe the test actions and verifications as sequential, human-readable instructions.

## 3. Debugging and Control Restrictions
- **No Manual Control Flow Bypassing**:
  - You are **NOT** allowed to skip `if` statements, manually adjust the Program Counter (PC), or force code jumps via `goto` commands during execution.
  - Exception: This is only permitted if a code block is physically impossible to reach and test otherwise.
- **Allowed: Modifying Variable States**:
  - You are fully permitted to modify memory or variable values in the debugger to satisfy conditions (e.g., altering a variable value to make an `if` statement evaluate to `True` so the nested code block executes).
- **Explicit and Diverse Debugger Steps**:
  - All debugger interactions must be written out with explicit actions. Avoid assuming implicit behavior.
  - Match the step paradigm to the specific testing goal:

    ### Case A: Verifying Function Reachability / Initialization
    1. Set breakpoint in function `[FunctionName]`.
    2. Run.
    3. Wait for Halt.
    4. Check that the function is reached.
    5. Run.
    6. Check that it is not reached again.

    ### Case B: Verifying Parameter Values
    1. Set breakpoint in function `[FunctionName]`.
    2. Run.
    3. Wait for Halt.
    4. Read parameter/argument `[ParameterName]`.
    5. Verify that `[ParameterName]` is equal to `[ExpectedValue]`.
    6. Run.

    ### Case C: Verifying Function Cyclicity
    1. Set breakpoint in function `[FunctionName]`.
    2. Run.
    3. Wait for Halt and record initial time `T1`.
    4. Run.
    5. Wait for Halt (next hit) and record time `T2`.
    6. Verify that the time delta (`T2 - T1`) corresponds to the expected cyclic interval (e.g., 10ms).
    7. Run.

## 4. Communication and Signal Restrictions
- **No CANoe Signals**:
  - You are **NOT** allowed to use CANoe signal manipulation or environment variables in test steps.
  - Exception: This is only permitted if it is the only possible way to execute the test (e.g., needing an active electrical load simulated to prevent a multicore ECU from immediately resetting or overwriting the inputs).

## 5. Output Formatting
- Generate the low-level test case designs directly under the `### Low Level Test Case Design` section inside each test case.
- Map the low-level test case steps to the corresponding high-level test case structure (e.g., matching the Given / When / Then sections).
- Be extremely explicit, unambiguous, and detail-oriented in every step.
"""

LOWLEVEL_HEADER = "### Low Level Test Case Design"
_LOWLEVEL_PLACEHOLDER = "*(Paste the low-level test cases generated by GitHub Copilot here)*"


# ---------------------------------------------------------------------------
# DB-backed prompt / rules
# ---------------------------------------------------------------------------

def _meta_get(db, key: str) -> Optional[str]:
    if db is not None and getattr(db, "is_open", False):
        try:
            return db.get_meta(key)
        except Exception:
            return None
    return None


def _meta_set(db, key: str, value: str) -> None:
    if db is not None and getattr(db, "is_open", False):
        db.set_meta(key, value)


def get_rules(db) -> str:
    return _meta_get(db, META_RULES) or DEFAULT_RULES


def get_prompt(db) -> str:
    return _meta_get(db, META_PROMPT) or DEFAULT_PROMPT


def set_rules(db, text: str) -> None:
    _meta_set(db, META_RULES, text)


def set_prompt(db, text: str) -> None:
    _meta_set(db, META_PROMPT, text)


# AI Part 2 — separate prompt/rules for the mind map and the chat (distinct keys,
# distinct defaults; editing these must never touch ai_prompt / ai_rules_md).
DEFAULT_MINDMAP_PROMPT = """Index this ECU source code into a compact map. For each architecture port/operation and each requirement, identify the implementing function(s) by name. Keep signatures and call/data-flow relationships; do not reproduce function bodies."""

DEFAULT_MINDMAP_RULES = """- Bind ports and requirements to functions by name/keyword evidence only; never invent a mapping.
- Prefer the most specific function (the one that reads/writes the named signal/parameter).
- Record file paths and signatures; omit bodies."""

DEFAULT_CHAT_RULES = """You are assisting with embedded-software validation for an ECU project. Use the provided mind map and the read-only code tools to ground every answer in the actual source. Cite function names and files. If you are unsure, inspect the code with the tools rather than guessing. Do not fabricate APIs, signals, or requirement traces."""


def get_mindmap_prompt(db) -> str:
    return _meta_get(db, META_MINDMAP_PROMPT) or DEFAULT_MINDMAP_PROMPT


def set_mindmap_prompt(db, text: str) -> None:
    _meta_set(db, META_MINDMAP_PROMPT, text)


def get_mindmap_rules(db) -> str:
    return _meta_get(db, META_MINDMAP_RULES) or DEFAULT_MINDMAP_RULES


def set_mindmap_rules(db, text: str) -> None:
    _meta_set(db, META_MINDMAP_RULES, text)


def get_chat_rules(db) -> str:
    return _meta_get(db, META_CHAT_RULES) or DEFAULT_CHAT_RULES


def set_chat_rules(db, text: str) -> None:
    _meta_set(db, META_CHAT_RULES, text)


# ---------------------------------------------------------------------------
# HLT file discovery / parsing
# ---------------------------------------------------------------------------

def hlt_output_dir(project_path: str) -> str:
    """The 'Test Case Design' folder next to the .arch project file."""
    return os.path.join(os.path.dirname(project_path), "Test Case Design")


def find_hlt_files(output_dir: str) -> List[str]:
    """Return generated HLT design files, sorted by name."""
    if not output_dir or not os.path.isdir(output_dir):
        return []
    return sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith("_Test_Case_Design.md")
    )


def parse_hlt_file(md_path: str) -> Dict:
    """Parse one HLT design file.

    Returns: {
        "model_name": str,
        "title": str,             # the file's H1 title
        "path": str,
        "test_cases": [ {index, id, title, raw, has_lowlevel}, ... ]
    }
    Each test case 'raw' is the full markdown block from its '## Test Case:'
    header up to (but excluding) the next test case / end of file.
    """
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = m.group(1).strip() if m else os.path.basename(md_path)
    model_name = title
    mm = re.search(r"Test Case Design\s*-\s*(.+)$", title)
    if mm:
        model_name = mm.group(1).strip()

    # Split on the '## Test Case:' headers, keeping each header with its body.
    parts = re.split(r"(?m)^(?=##\s+Test Case:)", text)
    cases: List[Dict] = []
    idx = 0
    for part in parts:
        hm = re.match(r"##\s+Test Case:\s*(.+)", part.strip())
        if not hm:
            continue
        tc_title = hm.group(1).splitlines()[0].strip()
        raw = part.rstrip()
        # Trim a trailing leading '---' separator that belongs to the next block
        has_ll = LOWLEVEL_HEADER in raw and _LOWLEVEL_PLACEHOLDER not in raw
        cases.append({
            "index": idx,
            "id": f"{idx}:{tc_title}",
            "title": tc_title,
            "raw": raw,
            "has_lowlevel": has_ll,
        })
        idx += 1

    return {"model_name": model_name, "title": title, "path": md_path, "test_cases": cases}


# ---------------------------------------------------------------------------
# Source-code context
# ---------------------------------------------------------------------------

_SRC_EXTS = (".c", ".h", ".cpp", ".hpp", ".cc")
_STOPWORDS = {
    "the", "and", "for", "are", "with", "that", "this", "test", "case", "given",
    "when", "then", "shall", "should", "must", "value", "verify", "check",
}


def extract_keywords(texts: List[str], limit: int = 40) -> List[str]:
    """Distinct lowercased tokens (>=3 chars, non-stopword) from the inputs."""
    seen: List[str] = []
    seen_set = set()
    for t in texts:
        for tok in re.split(r"[^A-Za-z0-9_]+", t or ""):
            tok = tok.lower()
            if len(tok) < 3 or tok in _STOPWORDS or tok in seen_set:
                continue
            seen_set.add(tok)
            seen.append(tok)
            if len(seen) >= limit:
                return seen
    return seen


def build_source_context(source, input_texts: List[str],
                         budget_chars: int = 12000) -> str:
    """Scan a source tree, score files by keyword relevance, and pack the most
    relevant content into a budget-limited context string.

    ``source`` may be a filesystem path (str) OR a SourceProvider (#2E, e.g. a
    release's source from the DB). Returns "" when there is no usable source.
    """
    if not source:
        return ""

    from Application_Logic.Logic_Source_Store import as_provider
    provider = as_provider(source)
    listed = [sf for sf in provider.list_files()
              if sf.rel_path.lower().endswith(_SRC_EXTS)]
    if not listed:
        return ""

    keywords = extract_keywords(input_texts)

    scored = []
    for sf in listed:
        content = provider.read_file(sf.rel_path)
        if content is None:
            continue
        lc = content.lower()
        name_lc = os.path.basename(sf.rel_path).lower()
        score = sum(lc.count(k) for k in keywords) + 5 * sum(k in name_lc for k in keywords)
        if score > 0:
            scored.append((score, sf.rel_path, content))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return ""

    parts = [f"[CODE CONTEXT — {len(listed)} source files scanned, "
             f"keywords: {', '.join(keywords[:10])}]\n"]
    used = len(parts[0])
    for _score, fp, content in scored:
        rel = os.path.basename(fp)
        header = f"\n/* ===== {rel} ===== */\n"
        remaining = budget_chars - used - len(header)
        if remaining <= 200:
            break
        snippet = content if len(content) <= remaining else content[:remaining] + "\n/* ...truncated... */"
        parts.append(header + snippet)
        used += len(header) + len(snippet)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Message assembly
# ---------------------------------------------------------------------------

def build_messages(rules: str, prompt: str, test_case_raw: str,
                   source_context: str = "") -> List[Dict[str, str]]:
    """Build the provider message list for generating ONE test case's low-level
    design. System carries the task prompt + rules; user carries the source
    context + the high-level test case."""
    system = f"{prompt}\n\n---\n# RULES\n{rules}"
    user_parts = []
    if source_context:
        user_parts.append(source_context)
    user_parts.append("# HIGH-LEVEL TEST CASE\n" + test_case_raw)
    user_parts.append(
        "\nGenerate ONLY the markdown content that belongs under the "
        f"'{LOWLEVEL_HEADER}' header for this test case. Do not repeat the "
        "high-level test case."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def clean_generated(text: str) -> str:
    """Normalise a model's low-level output before embedding it under our own
    '### Low Level Test Case Design' header.

    Models frequently echo that header back; if we then add our own we get a
    duplicate. Strip a leading echoed header (and any leading code-fence) so the
    section appears exactly once.
    """
    t = (text or "").strip()
    if t.startswith("```"):
        # Drop a leading ```markdown fence line if present.
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:].strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    if t.startswith(LOWLEVEL_HEADER):
        t = t[len(LOWLEVEL_HEADER):].lstrip()
    return t


def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^\w\-. ]", "_", name).strip()
    return safe or "model"


def write_lowlevel_output(output_dir: str, model_name: str, hlt_title: str,
                          test_cases: List[Dict],
                          generated: Dict[str, str]) -> str:
    """Write '<Model>_LowLevel.md'.

    test_cases: parsed cases (each with id/title/raw).
    generated:  {tc_id: low_level_markdown} for the generated subset.
    The file embeds each high-level case followed by its generated low-level
    design (or a note if not generated). Title derives from the HLT title.
    """
    os.makedirs(output_dir, exist_ok=True)
    fname = f"{sanitize_filename(model_name)}_LowLevel.md"
    fpath = os.path.join(output_dir, fname)

    out: List[str] = []
    ll_title = hlt_title.replace("Test Case Design", "Low-Level Test Case Design")
    if "Low-Level" not in ll_title:
        ll_title = f"Low-Level Test Case Design - {model_name}"
    out.append(f"# {ll_title}\n")
    out.append(f"Source architecture model: **{model_name}**\n")

    for tc in test_cases:
        if tc["id"] not in generated:
            continue
        out.append("\n---\n")
        # Reproduce the high-level block, then the generated low-level section.
        raw = tc["raw"]
        # Strip any existing placeholder/low-level section from the HLT block.
        raw = raw.split(LOWLEVEL_HEADER)[0].rstrip()
        out.append(raw)
        out.append(f"\n\n{LOWLEVEL_HEADER}\n")
        out.append(clean_generated(generated[tc["id"]]) + "\n")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return fpath


def apply_lowlevel_to_hlt(md_path: str, generated: Dict[str, str]) -> int:
    """Write generated low-level designs back INTO the original HLT file in place.

    Robust against whitespace: re-splits the *current* file text with the same
    regex parse_hlt_file uses (so each section is an exact substring), replaces
    the placeholder under each generated test case's '### Low Level...' header,
    and rejoins. Returns the number of test cases updated.

    Idempotent: a test case whose placeholder is already filled is left as-is
    (we only replace the placeholder text, never existing content).
    """
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    parts = re.split(r"(?m)^(?=##\s+Test Case:)", text)
    out: List[str] = []
    idx = 0
    updated = 0
    for part in parts:
        if part.startswith("## Test Case:"):
            title = part[len("## Test Case:"):].splitlines()[0].strip()
            tc_id = f"{idx}:{title}"
            idx += 1
            if tc_id in generated and _LOWLEVEL_PLACEHOLDER in part:
                part = part.replace(
                    _LOWLEVEL_PLACEHOLDER, clean_generated(generated[tc_id]), 1)
                updated += 1
        out.append(part)

    if updated:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("".join(out))
    return updated


# ===========================================================================
# Phase 8 — Code diff engine + mind-map builder (pure, no Qt)
# ===========================================================================

MINDMAP_BUILDER_VERSION = "2.0"
_MM_SRC_EXTS = (".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx")
# Locked decision #3: file reads are effectively uncapped (high safety ceiling).
_DIFF_PER_FILE_CAP = 4_000_000
_DIFF_SKIP_BYTES = 4_000_000
_DIFF_MAX_FILES = 4000


def _iter_source_files(root: str, exts=_MM_SRC_EXTS):
    """Yield (relpath, abspath, size, mtime_ns) for every source file, stats only."""
    if not root or not os.path.isdir(root):
        return
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            if n.lower().endswith(exts):
                ap = os.path.join(dirpath, n)
                try:
                    st = os.stat(ap)
                except OSError:
                    continue
                rel = os.path.relpath(ap, root).replace(os.sep, "/")
                yield rel, ap, st.st_size, st.st_mtime_ns


def hash_source_tree(source, exts=_MM_SRC_EXTS) -> str:
    """Cheap staleness probe: SHA256 over sorted (relpath, change_key).

    ``source`` may be a path or a SourceProvider (#2E). For a filesystem source the
    change_key is (size, mtime) — stats only, never reads bodies (honours the EDR
    per-syscall I/O constraint). For a DB release source it's the stored content
    hash (exact). Documented false modes for the filesystem case (acceptable for a
    *manual* staleness hint): a clean rebuild rewrites mtimes (false 'stale'); a
    size+mtime preserving copy looks fresh. Regeneration is always user-initiated."""
    from Application_Logic.Logic_Source_Store import as_provider
    provider = as_provider(source)
    h = hashlib.sha256()
    files = [sf for sf in provider.list_files() if sf.rel_path.lower().endswith(exts)]
    for sf in sorted(files, key=lambda s: s.rel_path):
        key = "|".join(str(x) for x in provider.change_key(sf))
        h.update(f"{sf.rel_path}|{key}\n".encode("utf-8"))
    return h.hexdigest()


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def diff_source_folders(current, previous,
                        exts=_MM_SRC_EXTS, context_lines: int = 3,
                        per_file_cap: int = _DIFF_PER_FILE_CAP,
                        max_files: int = _DIFF_MAX_FILES,
                        skip_file_bytes: int = _DIFF_SKIP_BYTES) -> List[Dict]:
    """File-by-file unified diff between two sources (paths or SourceProviders, #2E).

    Two-stage to bound reads under EDR: list both sources first; if a file's
    change_key is IDENTICAL in both (filesystem: size+mtime; DB: content hash), it
    is treated as unchanged and its bytes are NEVER read. Only differing pairs (and
    added/deleted files) are read and confirmed. Returns [{file_path, status,
    unified_diff}] where status is 'modified' | 'added' | 'deleted'.
    """
    from Application_Logic.Logic_Source_Store import as_provider
    cur_p = as_provider(current)
    prev_p = as_provider(previous)
    cur = {sf.rel_path: sf for sf in cur_p.list_files()
           if sf.rel_path.lower().endswith(exts)}
    prev = {sf.rel_path: sf for sf in prev_p.list_files()
            if sf.rel_path.lower().endswith(exts)}
    results: List[Dict] = []
    all_rel = sorted(set(cur) | set(prev))
    total = len(all_rel)
    logger.info("Comparing %d source files…", total)

    for idx, rel in enumerate(all_rel):
        # Periodic progress — on EDR machines each read is scanned, so this can be
        # slow; the loading window shows it's making progress rather than hung.
        if total and (idx % 25 == 0 or idx == total - 1):
            logger.info("Diffing files… %d/%d", idx + 1, total)
        if len(results) >= max_files:
            results.append({"file_path": "(truncated)", "status": "modified",
                            "unified_diff": f"(diff truncated: more than {max_files} files)"})
            break
        in_cur, in_prev = rel in cur, rel in prev

        # Stat-gate: identical change_key in both -> unchanged, skip the READ.
        if in_cur and in_prev:
            sc, sp = cur[rel].size, prev[rel].size
            if cur_p.change_key(cur[rel]) == prev_p.change_key(prev[rel]):
                continue
            if sc > skip_file_bytes or sp > skip_file_bytes:
                # Confirm by size only; avoid reading huge files.
                if sc != sp:
                    results.append({"file_path": rel, "status": "modified",
                                    "unified_diff": "(diff omitted: file too large)"})
                continue
            old = prev_p.read_file(rel) or ""
            new = cur_p.read_file(rel) or ""
            if old == new:
                continue   # same bytes despite differing change_key
            status = "modified"
        elif in_cur:
            if cur[rel].size > skip_file_bytes:
                results.append({"file_path": rel, "status": "added",
                                "unified_diff": "(diff omitted: file too large)"})
                continue
            old, new = "", cur_p.read_file(rel) or ""
            status = "added"
        else:
            if prev[rel].size > skip_file_bytes:
                results.append({"file_path": rel, "status": "deleted",
                                "unified_diff": "(diff omitted: file too large)"})
                continue
            old, new = prev_p.read_file(rel) or "", ""
            status = "deleted"

        ud = "".join(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=rel, tofile=rel, n=context_lines))
        results.append({"file_path": rel, "status": status,
                        "unified_diff": ud[:per_file_cap]})
    return results


def compute_diff_hash(current_root, previous_root) -> str:
    """Stable, order-independent id for a (current, previous) source pair."""
    h = hashlib.sha256()
    h.update(hash_source_tree(current_root).encode())
    h.update(b"|")
    h.update(hash_source_tree(previous_root).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Mind map (compact per-model index)
# ---------------------------------------------------------------------------

def build_mind_map(source_path: str, model_name: str, model_id: int,
                   ports: List[Dict], requirements: List[Dict],
                   generated_at: str = "", code_map: Optional[Dict] = None) -> Dict:
    """Build the compact CompactMindMap for one architecture model.

    ports:        [{"name", "operation"(opt), "requirement_traces"(opt list)}]
    requirements: [{"id", "text"}]  (already parsed via parse_requirements_file)

    Omits function BODIES (token blow-up) — keeps signatures + relationships +
    keyword-inferred port/requirement→function bindings. Bindings live ONLY in
    the mind map, never written back to the architecture table.
    """
    from . import Logic_Code_Index as ck  # ported indexer (Phase 7.5)

    idx = ck.build_index(source_path) if source_path else None

    functions: Dict[str, Dict] = {}
    files: Dict[str, List[str]] = {}
    if idx is not None:
        for name, f in idx.functions.items():
            functions[name] = {
                "file": f.relpath, "signature": f.signature,
                "calls": list(f.calls), "reads": list(f.reads_vars),
                "writes": list(f.writes_vars),
            }
        for relpath, fnames in idx.file_functions.items():
            files[relpath] = [idx.functions[n].signature for n in fnames if n in idx.functions]

    def _bind(text: str, limit: int) -> List[str]:
        if idx is None or not text.strip():
            return []
        kws = ck.extract_keywords(text)
        return [fn.name for _score, fn in idx.find_functions_by_keywords(kws, max_results=limit)]

    ports_map: Dict[str, Dict] = {}
    for i, p in enumerate(ports or []):
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        op = str(p.get("operation", "")).strip()
        impl = _bind(f"{name} {op}", 4)
        ports_map[f"{i}:{name}"] = {
            "name": name, "operation": op,
            "implementing_funcs": impl,
            "files": sorted({functions[n]["file"] for n in impl if n in functions}),
            "requirement_traces": list(p.get("requirement_traces", []) or []),
        }

    reqs_map: Dict[str, Dict] = {}
    for req in requirements or []:
        rid = str(req.get("id", "")).strip()
        text = str(req.get("text", "")).strip()
        if not rid:
            continue
        kws = ck.extract_keywords(text) if idx is not None else []
        reqs_map[rid] = {
            "text": text, "keywords": kws[:10],
            "implementing_funcs": _bind(text, 5),
        }

    return {
        "builder_version": MINDMAP_BUILDER_VERSION,
        "model_id": model_id,
        "model_name": model_name,
        "source_hash": hash_source_tree(source_path) if source_path else "",
        "generated_at": generated_at,
        "files": files,
        "functions": functions,
        "ports": ports_map,
        "requirements": reqs_map,
        "structures": code_map.get("structures", {}) if code_map else {},
        "global_variables": code_map.get("global_variables", {}) if code_map else {},
    }


def _render_mind_map_v1(mm: Dict, budget_chars: int) -> str:
    """v1.0 renderer: ports -> requirements -> flat function index, truncating
    the FUNCTION INDEX last so ports/requirements always survive the budget."""
    head = [f"# MIND MAP — {mm.get('model_name', '')}",
            f"(builder {mm.get('builder_version', '?')}; "
            f"{len(mm.get('functions', {}))} functions, "
            f"{len(mm.get('ports', {}))} ports, "
            f"{len(mm.get('requirements', {}))} requirements)\n"]

    ports_lines = ["## PORTS"]
    for _k, p in (mm.get("ports") or {}).items():
        impl = ", ".join(p.get("implementing_funcs", [])) or "(no code match)"
        traces = ", ".join(p.get("requirement_traces", []))
        line = f"- {p['name']}" + (f" :: {p['operation']}" if p.get("operation") else "")
        line += f"  -> {impl}"
        if traces:
            line += f"  [req: {traces}]"
        ports_lines.append(line)
    if len(ports_lines) == 1:
        ports_lines.append("(none)")

    req_lines = ["\n## REQUIREMENTS"]
    for rid, r in (mm.get("requirements") or {}).items():
        impl = ", ".join(r.get("implementing_funcs", [])) or "(no code match)"
        req_lines.append(f"- {rid}: {r.get('text', '')[:160]}  -> {impl}")
    if len(req_lines) == 1:
        req_lines.append("(none)")

    fixed = "\n".join(head + ports_lines + req_lines)
    fn_header = "\n\n## FUNCTION INDEX (signatures only)\n"

    # Fill the remaining budget with function signatures, truncating LAST.
    # Reserve space for the worst-case "omitted" note so the final cap can never
    # slice the note off.
    funcs = mm.get("functions") or {}
    note_tmpl = "(+{n} more functions omitted — use search_code/read_file for details)\n"
    reserve = len(note_tmpl.format(n=len(funcs))) if funcs else 0
    budget_for_fns = max(0, budget_chars - len(fixed) - len(fn_header) - reserve)
    fn_lines, used, dropped = [], 0, 0
    for name, f in funcs.items():
        entry = f"- {f.get('signature') or name}  [{f.get('file', '')}]\n"
        if used + len(entry) > budget_for_fns:
            dropped += 1
            continue
        fn_lines.append(entry)
        used += len(entry)
    body = fixed + fn_header + "".join(fn_lines)
    if dropped:
        body += note_tmpl.format(n=dropped)
    return body[:budget_chars]


def _render_mind_map_v2(mm: Dict, budget_chars: int) -> str:
    """v2.0 renderer: ports -> requirements -> structures -> globals -> flat function index,
    truncating sections bottom-up so critical high-level context survives."""
    head = [f"# MIND MAP v2.0 — {mm.get('model_name', '')}",
            f"(builder 2.0; "
            f"{len(mm.get('functions', {}))} functions, "
            f"{len(mm.get('ports', {}))} ports, "
            f"{len(mm.get('requirements', {}))} requirements, "
            f"{len(mm.get('structures', {}))} structures, "
            f"{len(mm.get('global_variables', {}))} global variables)\n"]
    fixed_header = "\n".join(head)

    ports_lines = ["## PORTS"]
    for _k, p in (mm.get("ports") or {}).items():
        impl = ", ".join(p.get("implementing_funcs", [])) or "(no code match)"
        traces = ", ".join(p.get("requirement_traces", []))
        line = f"- {p['name']}" + (f" :: {p['operation']}" if p.get("operation") else "")
        line += f"  -> {impl}"
        if traces:
            line += f"  [req: {traces}]"
        ports_lines.append(line)
    if len(ports_lines) == 1:
        ports_lines.append("(none)")
    ports_text = "\n".join(ports_lines)

    req_lines = ["\n## REQUIREMENTS"]
    for rid, r in (mm.get("requirements") or {}).items():
        impl = ", ".join(r.get("implementing_funcs", [])) or "(no code match)"
        req_lines.append(f"- {rid}: {r.get('text', '')[:160]}  -> {impl}")
    if len(req_lines) == 1:
        req_lines.append("(none)")
    reqs_text = "\n".join(req_lines)

    def format_struct(s):
        fields_str = ", ".join(f"{f['name']}: {f['type']}" for f in s[1][:10])
        omitted = ", ..." if len(s[1]) > 10 else ""
        return f"- struct {s[0]} {{ {fields_str}{omitted} }}"

    # Dynamic sections supporting bottom-up budget packing
    funcs = mm.get("functions") or {}
    sections = [
        ("\n## STRUCTURES & CLASSES", list((mm.get("structures") or {}).items()),
         format_struct,
         "(+{n} more structures omitted)\n"),
        ("\n## GLOBAL VARIABLES", list((mm.get("global_variables") or {}).items()),
         lambda g: f"- {g[1]} {g[0]}",
         "(+{n} more global variables omitted)\n"),
        ("\n## FUNCTION INDEX (signatures only)", list(funcs.items()),
         lambda f: f"- {f[1].get('signature') or f[0]}  [{f[1].get('file', '')}]",
         "(+{n} more functions omitted — use search_code/read_file for details)\n")
    ]

    out_parts = [fixed_header, ports_text, reqs_text]
    current_len = sum(len(p) for p in out_parts)

    for sec_title, items, format_fn, note_tmpl in sections:
        sec_header = "\n" + sec_title + "\n"
        if not items:
            sec_text = sec_header + "(none)\n"
            if current_len + len(sec_text) <= budget_chars:
                out_parts.append(sec_text)
                current_len += len(sec_text)
            continue

        reserve = len(note_tmpl.format(n=len(items)))
        budget_for_sec = budget_chars - current_len - len(sec_header) - reserve

        if budget_for_sec <= 200:
            note = note_tmpl.format(n=len(items))
            if current_len + len(sec_header) + len(note) <= budget_chars:
                out_parts.append(sec_header + note)
                current_len += len(sec_header) + len(note)
            break

        sec_lines = []
        used = 0
        dropped = 0
        for item in items:
            line = format_fn(item) + "\n"
            if used + len(line) > budget_for_sec:
                dropped += 1
                continue
            sec_lines.append(line)
            used += len(line)

        sec_body = sec_header + "".join(sec_lines)
        if dropped:
            sec_body += note_tmpl.format(n=dropped)

        out_parts.append(sec_body)
        current_len += len(sec_body)

    return "".join(out_parts)[:budget_chars]


def mind_map_to_text(mind_map: Optional[Dict], budget_chars: int = 14000) -> str:
    """Render a mind map to compact, LLM-friendly text within budget. Injected
    per request INSTEAD of raw C (Phase 12). Version-dispatched and defensive:
    an unknown/older builder_version still renders (no KeyError) with a note."""
    if not mind_map:
        return "(no mind map available — generate one in the Advanced AI Chat tab)"
    version = mind_map.get("builder_version", "")
    if version == "2.0":
        text = _render_mind_map_v2(mind_map, budget_chars)
    else:
        text = _render_mind_map_v1(mind_map, budget_chars)
        
    if version != MINDMAP_BUILDER_VERSION:
        note = ("\n(Note: mind map built by a different version "
                f"'{version or 'unknown'}'; regenerate for full fidelity.)\n")
        text = (text + note)[:budget_chars]
    return text


def mind_map_char_count(mind_map: Optional[Dict]) -> int:
    return len(mind_map_to_text(mind_map, budget_chars=10_000_000))


def mindmap_button_label(has_diff: bool) -> str:
    """Locked decision #6: the Generate→Regenerate flip is driven purely by
    whether diffs exist (a cheap DB check), never by a filesystem scan."""
    return "Regenerate Mind Map" if has_diff else "Generate Mind Map"


# ---------------------------------------------------------------------------
# Requirements import (CSV / XLSX)
# ---------------------------------------------------------------------------

_REQ_ID_HINTS = ("requirement id", "req id", "reqid", "requirement", "req", "id")
_REQ_TEXT_HINTS = ("requirement text", "description", "text", "desc", "summary")


def parse_requirements_file(file_path: str, max_rows: int = 500) -> List[Dict]:
    """Parse a CSV/XLSX requirements sheet into [{"id","text"}].

    Reuses the PUBLIC reader in Logic_Rhapsody_Import (read_file → (columns,
    rows-as-dicts)); does not touch private internals. Auto-detects id/text
    columns case-insensitively, falling back to the first two columns. Truncates
    at max_rows with a sentinel row.
    """
    from Application_Logic.Logic_Rhapsody_Import import read_file
    logger.info("Reading requirements sheet: %s", os.path.basename(file_path))
    columns, rows = read_file(file_path)
    if not columns:
        return []
    logger.info("Parsing %d requirement row(s)…", len(rows))

    def _pick(hints):
        for h in hints:
            for c in columns:
                if c and c.strip().lower() == h:
                    return c
        for h in hints:
            for c in columns:
                if c and h in c.strip().lower():
                    return c
        return None

    id_col = _pick(_REQ_ID_HINTS) or columns[0]
    text_col = _pick(_REQ_TEXT_HINTS)
    if text_col is None or text_col == id_col:
        text_col = columns[1] if len(columns) > 1 else columns[0]

    out: List[Dict] = []
    for row in rows:
        rid = str(row.get(id_col, "")).strip()
        text = str(row.get(text_col, "")).strip()
        if not rid and not text:
            continue
        out.append({"id": rid or f"R{len(out) + 1}", "text": text})
        if len(out) >= max_rows:
            break
    total = sum(1 for r in rows if str(r.get(id_col, "")).strip() or str(r.get(text_col, "")).strip())
    if total > len(out):
        out.append({"id": "...", "text": f"({total - len(out)} more requirements omitted)"})
    return out

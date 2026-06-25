"""
Source-Level Test Code Injection — matching engine
==================================================
The injection feature splices test snippets into production C source without
storing brittle line *numbers* (which rot the moment anyone edits the file
upstream). Instead each hook records the *text* of the line immediately above
and below the splice point. This module re-finds that splice point as the source
shifts underneath, and shifts a hook up/down while keeping it inside the target
function's braces.

Confidence is reported out of 4:
  * 4/4 — both anchors found, in order (exact splice point).
  * 3/4 — only one anchor found (we infer the point from that single side).
  * 0/4 — neither anchor found, or the anchors disagree → a *conflict*. The UI
    renders a "+line" placeholder the user can reposition by hand.

The DB row (``test_code_injections``) and ``Logic_Database`` own persistence;
this module is pure logic so it stays unit-testable without a project file.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Confidence scores (out of CONFIDENCE_MAX). The UI treats anything below
# CONFIDENCE_OK as a conflict.
CONFIDENCE_MAX = 4
CONFIDENCE_EXACT = 4   # both anchors, in order
CONFIDENCE_SINGLE = 3  # one anchor only
CONFIDENCE_NONE = 0    # conflict

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def clean_line(line: str) -> str:
    """Normalise a line for anchor comparison: drop trailing comments + whitespace.

    Removes ``/* ... */`` spans and anything after ``//`` (the common case of a
    comment a developer added/removed without meaning to move the hook), then
    collapses surrounding whitespace. Returns ``""`` for blank/comment-only lines.
    """
    if line is None:
        return ""
    s = _BLOCK_COMMENT.sub("", line)
    idx = s.find("//")
    if idx != -1:
        s = s[:idx]
    return s.strip()


def _find_clean(file_lines: List[str], target: str, start: int = 0) -> int:
    """Index of the first line at/after ``start`` whose cleaned text equals
    ``target`` (already cleaned). -1 if not found or ``target`` is empty."""
    if not target:
        return -1
    for i in range(start, len(file_lines)):
        if clean_line(file_lines[i]) == target:
            return i
    return -1


def resolve_injection(file_lines: List[str], line_above: str,
                      line_below: str) -> dict:
    """Locate the splice point for a hook; return ``{index, confidence, anchor}``.

    ``index`` is the 0-based position at which the injected block is inserted
    (the number of existing lines above it), or ``None`` on a conflict.
    ``confidence`` is out of :data:`CONFIDENCE_MAX`. ``anchor`` is one of
    ``"both" | "above" | "below" | "none"`` describing what matched.
    """
    above = clean_line(line_above)
    below = clean_line(line_below)

    above_idx = _find_clean(file_lines, above) if above else -1
    # Prefer a below-anchor that comes after the above-anchor (keeps the pair in
    # order even when the same text appears more than once).
    below_idx = -1
    if below:
        search_from = above_idx + 1 if above_idx != -1 else 0
        below_idx = _find_clean(file_lines, below, search_from)
        if below_idx == -1 and above_idx != -1:
            below_idx = _find_clean(file_lines, below)  # fall back to any match

    if above_idx != -1 and below_idx != -1 and above_idx < below_idx:
        # Both anchors, in order — splice right after the above-anchor.
        return {"index": above_idx + 1, "confidence": CONFIDENCE_EXACT,
                "anchor": "both"}
    if above_idx != -1:
        return {"index": above_idx + 1, "confidence": CONFIDENCE_SINGLE,
                "anchor": "above"}
    if below_idx != -1:
        return {"index": below_idx, "confidence": CONFIDENCE_SINGLE,
                "anchor": "below"}
    return {"index": None, "confidence": CONFIDENCE_NONE, "anchor": "none"}


def resolve_injection_index(file_lines: List[str], line_above: str,
                            line_below: str) -> Optional[int]:
    """The 0-based splice index for a hook, or ``None`` on a conflict.

    Thin wrapper over :func:`resolve_injection` for callers that only need the
    position (the spec's primary entry point).
    """
    return resolve_injection(file_lines, line_above, line_below)["index"]


def function_bounds(code_index, function_name: str) -> Optional[Tuple[int, int]]:
    """``(line_start, line_end)`` (1-based) for a function from a built
    ``Logic_Code_Index.CodeIndex``, or ``None`` if it isn't indexed."""
    if not code_index or not function_name:
        return None
    func = getattr(code_index, "functions", {}).get(function_name)
    if func is None:
        return None
    return (func.line_start, func.line_end)


def _within_function(index: int, func_bounds: Optional[Tuple[int, int]],
                     n_lines: int) -> bool:
    """True if a 0-based splice ``index`` stays inside the function body.

    ``func_bounds`` is 1-based ``(line_start, line_end)`` where ``line_start`` is
    the signature line and ``line_end`` the closing-brace line. The block must
    sit strictly below the signature (so below the opening brace) and at/above
    the closing brace.
    """
    if func_bounds is None:
        return 0 <= index <= n_lines
    start, end = func_bounds
    lo = start            # 0-based: first line of the body (after the signature)
    hi = end - 1          # 0-based index of the closing-brace line; insert before it
    return lo <= index <= hi


def shift_injection(file_lines: List[str], injection_id: int,
                    direction: str, db, code_index=None,
                    func_bounds: Optional[Tuple[int, int]] = None) -> dict:
    """Move a hook one line ``"up"`` or ``"down"`` and re-anchor it in the DB.

    Boundaries come from ``Logic_Code_Index`` (pass a built ``code_index`` or an
    explicit ``func_bounds``); a shift that would carry the block out of the
    target function's braces is refused. On success the new ``line_above_code`` /
    ``line_below_code`` anchors are written and ``offset_lines`` is nudged.

    Returns ``{"ok": bool, ...}``; on refusal ``ok`` is False with a ``reason``.
    """
    if direction not in ("up", "down"):
        return {"ok": False, "reason": f"Unknown direction: {direction}"}
    inj = db.get_injection(injection_id)
    if inj is None:
        return {"ok": False, "reason": f"No such injection: {injection_id}"}

    cur = resolve_injection(file_lines, inj["line_above_code"],
                            inj["line_below_code"])
    index = cur["index"]
    if index is None:
        return {"ok": False, "reason": "Anchor conflict — resolve the hook first."}

    if func_bounds is None and code_index is not None:
        func_bounds = function_bounds(code_index, inj["function_name"])

    new_index = index - 1 if direction == "up" else index + 1
    n = len(file_lines)
    if not _within_function(new_index, func_bounds, n):
        return {"ok": False,
                "reason": "Cannot move the block outside the function body."}

    new_above = file_lines[new_index - 1] if new_index - 1 >= 0 else ""
    new_below = file_lines[new_index] if new_index < n else ""
    new_offset = int(inj.get("offset_lines") or 0) + (-1 if direction == "up" else 1)
    db.update_injection_anchors(injection_id, new_above, new_below,
                                offset_lines=new_offset)
    return {"ok": True, "index": new_index, "line_above_code": new_above,
            "line_below_code": new_below, "offset_lines": new_offset}


def apply_injections(file_text: str, injections: List[dict]) -> Tuple[str, List[dict]]:
    """Splice every resolvable hook in ``injections`` into ``file_text``.

    Returns ``(new_text, results)`` where each result is ``{injection_id, index,
    confidence, applied}``. Insertions are applied bottom-up so earlier indices
    stay valid, and conflicts (confidence 0) are skipped and reported.
    """
    lines = file_text.splitlines()
    keep_trailing_nl = file_text.endswith("\n")

    resolved = []
    for inj in injections:
        r = resolve_injection(lines, inj.get("line_above_code", ""),
                              inj.get("line_below_code", ""))
        resolved.append((inj, r))

    results = []
    # Apply highest index first so lower insertions don't shift pending ones.
    for inj, r in sorted(resolved, key=lambda t: (t[1]["index"] is None,
                                                  t[1]["index"] or 0),
                         reverse=True):
        idx = r["index"]
        applied = False
        if idx is not None:
            snippet = (inj.get("injected_code") or "").splitlines()
            lines[idx:idx] = snippet
            applied = True
        results.append({"injection_id": inj.get("id"), "index": idx,
                        "confidence": r["confidence"], "applied": applied})

    new_text = "\n".join(lines)
    if keep_trailing_nl and new_text and not new_text.endswith("\n"):
        new_text += "\n"
    # Preserve the original order of results for the caller.
    order = {inj.get("id"): i for i, inj in enumerate(injections)}
    results.sort(key=lambda d: order.get(d["injection_id"], 0))
    return new_text, results

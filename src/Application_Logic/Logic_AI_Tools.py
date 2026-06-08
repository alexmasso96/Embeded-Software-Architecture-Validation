"""
AI agent tools (Phase 9) — a small set of READ-ONLY, sandboxed tools the chat
agent can call to ground its answers in the real codebase.

Safety: every filesystem tool is path-jailed under a single sandbox root via
`_contain` (realpath both sides + os.sep boundary guard, Windows-case aware).
There is NO write capability and NO execution. If no sandbox root is configured
the file tools refuse rather than falling back to the current working directory.

File reads are effectively uncapped (4 MB safety ceiling, locked decision #3) —
embedded C files bundle many functions and balloon; the model must read them
whole when asked. The agent loop additionally enforces a cumulative output cap.
"""
from __future__ import annotations

import fnmatch
import os
from typing import List, Optional

from .Logic_AI_Providers import Tool

READ_CAP = 4_000_000           # 4 MB per read/diff (decision #3)
REQ_CAP = 64_000               # requirements render cap
MAX_LIST = 200
MAX_SEARCH_MATCHES = 100
# The read-only tools work on whatever source the user points at — broader than
# the C-focused mind-map indexer, so they also serve Python/other repos (and the
# "inception" case of pointing at this app's own source).
_SRC_EXTS = (".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
             ".py", ".pyw", ".rs", ".go", ".java", ".js", ".ts")


class ToolError(Exception):
    """Raised for sandbox violations / bad tool input (returned to the model)."""


def default_tools() -> List[Tool]:
    """Provider-neutral definitions for the read-only tool set."""
    return [
        Tool("read_file", "Read a source file (path relative to the source root).",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
        Tool("list_files", "List source files matching a glob under the source root.",
             {"type": "object", "properties": {"pattern": {"type": "string"}}}),
        Tool("search_code", "Search the source for a substring; returns file:line matches.",
             {"type": "object", "properties": {"query": {"type": "string"},
                                               "path": {"type": "string"}}, "required": ["query"]}),
        Tool("get_mind_map", "Get the compact mind-map index for the current model.",
             {"type": "object", "properties": {}}),
        Tool("get_requirements", "Get the imported requirements for the current project.",
             {"type": "object", "properties": {}}),
        Tool("get_diff", "Get the code diff (all files, or one file_path) vs the previous source.",
             {"type": "object", "properties": {"file_path": {"type": "string"}}}),
        Tool("get_function", "Get detailed properties, reads/writes, and conditions of a function.",
             {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
        Tool("get_call_graph", "Get the call graph (callers/callees) around a function up to a specific depth.",
             {"type": "object", "properties": {
                 "name": {"type": "string"},
                 "depth": {"type": "integer", "default": 1},
                 "direction": {"type": "string", "enum": ["forward", "backward", "both"], "default": "both"}
             }, "required": ["name"]}),
    ]


class ToolExecutor:
    def __init__(self, source_root: Optional[str], db=None,
                 model_id: int = -1, diff_hash: str = ""):
        self.source_root = source_root
        self.db = db
        self.model_id = model_id
        self.diff_hash = diff_hash

    # ------------------------------------------------------------------
    # Path jail
    # ------------------------------------------------------------------
    def _contain(self, candidate: str) -> str:
        if not self.source_root:
            raise ToolError("No source sandbox configured; file tools are disabled.")
        if not isinstance(candidate, str) or not candidate.strip():
            raise ToolError("Empty path.")
        root = os.path.realpath(self.source_root)
        target = os.path.realpath(os.path.join(root, candidate))
        nroot, ntarget = os.path.normcase(root), os.path.normcase(target)
        # The '+ os.sep' guard stops '/root-evil' from matching '/root'.
        if ntarget != nroot and not ntarget.startswith(nroot + os.sep):
            raise ToolError("Path escapes the sandbox root.")
        return target

    def _rel(self, abspath: str) -> str:
        return os.path.relpath(abspath, os.path.realpath(self.source_root)).replace(os.sep, "/")

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def read_file(self, path: str) -> str:
        target = self._contain(path)
        if not os.path.isfile(target):
            raise ToolError(f"Not a file: {path}")
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(READ_CAP + 1)
        if len(data) > READ_CAP:
            return data[:READ_CAP] + "\n/* ...truncated at 4MB... */"
        return data

    def list_files(self, pattern: str = "*") -> str:
        self._contain(".")                       # ensures a sandbox is configured
        root = os.path.realpath(self.source_root)
        pat = pattern or "*"
        out = []
        for dirpath, _dirs, names in os.walk(root):
            for n in names:
                if not n.lower().endswith(_SRC_EXTS):
                    continue
                ap = os.path.join(dirpath, n)
                rel = self._rel(ap)
                if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(n, pat):
                    try:
                        self._contain(rel)        # re-validate EVERY result
                    except ToolError:
                        continue
                    out.append(rel)
                    if len(out) >= MAX_LIST:
                        out.append(f"(+more — refine the pattern; capped at {MAX_LIST})")
                        return "\n".join(out)
        return "\n".join(out) if out else "(no matching files)"

    def search_code(self, query: str, path: str = ".") -> str:
        if not query:
            raise ToolError("Empty query.")
        base = self._contain(path)
        files = [base] if os.path.isfile(base) else []
        if os.path.isdir(base):
            for dirpath, _dirs, names in os.walk(base):
                files += [os.path.join(dirpath, n) for n in names
                          if n.lower().endswith(_SRC_EXTS)]
        out, q = [], query.lower()
        for ap in files:
            try:
                self._contain(self._rel(ap))      # re-validate
            except ToolError:
                continue
            try:
                with open(ap, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if q in line.lower():
                            out.append(f"{self._rel(ap)}:{i}: {line.strip()[:200]}")
                            if len(out) >= MAX_SEARCH_MATCHES:
                                out.append(f"(+more — capped at {MAX_SEARCH_MATCHES})")
                                return "\n".join(out)
            except OSError:
                continue
        return "\n".join(out) if out else "(no matches)"

    def get_mind_map(self) -> str:
        if self.db is None:
            return "(no project database)"
        from . import Logic_AI_Context as ctx
        mm = self.db.get_model_mindmap(self.model_id)
        return ctx.mind_map_to_text(mm)

    def get_requirements(self) -> str:
        if self.db is None:
            return "(no project database)"
        import json
        from . import Logic_AI_Context as ctx
        raw = self.db.get_meta(ctx.META_REQUIREMENTS)
        if not raw:
            return "(no requirements imported)"
        try:
            reqs = json.loads(raw)
        except (ValueError, TypeError):
            return "(requirements unreadable)"
        lines = [f"- {r.get('id', '')}: {r.get('text', '')}" for r in reqs]
        return ("\n".join(lines))[:REQ_CAP]

    def get_diff(self, file_path: Optional[str] = None) -> str:
        if self.db is None or not self.diff_hash:
            return "(no diff available — generate diffs first)"
        diffs = self.db.get_code_diffs(self.model_id, self.diff_hash)
        if file_path:
            diffs = [d for d in diffs if d["file_path"] == file_path]
            if not diffs:
                return f"(no diff for {file_path})"
        blob = "\n".join(f"=== {d['file_path']} ({d['status']}) ===\n{d['unified_diff']}"
                         for d in diffs)
        return blob[:READ_CAP]

    def get_function(self, name: str) -> str:
        if self.db is None:
            return "(no project database)"
        code_map = self.db.get_model_code_map(self.model_id)
        if not code_map or "functions" not in code_map:
            return "(no code map available)"
        
        funcs = code_map["functions"]
        if name not in funcs:
            matches = [f for f in funcs if name.lower() in f.lower()]
            if not matches:
                return f"(function '{name}' not found)"
            if len(matches) > 1:
                return f"(function '{name}' not found. Did you mean: {', '.join(matches[:5])}?)"
            name = matches[0]
            
        f = funcs[name]
        lines = [
            f"Function: {name}",
            f"  File: {f.get('file', 'unknown') or 'unknown'}",
            f"  Line: {f.get('line_start', 0)}",
            f"  Address: {hex(f.get('address', 0)) if isinstance(f.get('address'), int) else f.get('address')}",
            f"  Size: {f.get('size', 0)} bytes",
            f"  Signature: {f.get('signature', '')}",
            f"  Return Type: {f.get('return_type', '')}",
            "  Parameters:"
        ]
        for p in f.get("parameters", []):
            lines.append(f"    - {p.get('name')}: {p.get('type')}")
        lines.append("  Calls out to:")
        for c in f.get("calls", []):
            lines.append(f"    - {c}")
        lines.append("  Reads variables:")
        for r in f.get("reads_vars", []):
            lines.append(f"    - {r}")
        lines.append("  Writes variables:")
        for w in f.get("writes_vars", []):
            lines.append(f"    - {w}")
        lines.append("  Conditions:")
        for cond in f.get("conditions", []):
            lines.append(f"    - {cond}")
        return "\n".join(lines)

    def get_call_graph(self, name: str, depth: int = 1, direction: str = "both") -> str:
        if self.db is None:
            return "(no project database)"
        code_map = self.db.get_model_code_map(self.model_id)
        if not code_map or "functions" not in code_map:
            return "(no code map available)"
            
        funcs = code_map["functions"]
        if name not in funcs:
            matches = [f for f in funcs if name.lower() in f.lower()]
            if not matches:
                return f"(function '{name}' not found)"
            if len(matches) > 1:
                return f"(function '{name}' not found. Did you mean: {', '.join(matches[:5])}?)"
            name = matches[0]

        callers_map = {f: [] for f in funcs}
        for f_caller, f_data in funcs.items():
            for callee in f_data.get("calls", []):
                if callee in callers_map:
                    callers_map[callee].append(f_caller)
                    
        lines = []
        
        if direction in ("forward", "both"):
            lines.append(f"Callee Graph for {name} (Depth {depth}):")
            visited = set()
            def _walk_forward(curr, curr_depth, indent):
                if curr_depth > depth or curr in visited:
                     return
                visited.add(curr)
                callees = funcs.get(curr, {}).get("calls", [])
                for callee in callees:
                    lines.append(f"{indent}-> {callee}")
                    _walk_forward(callee, curr_depth + 1, indent + "  ")
            _walk_forward(name, 1, "  ")
            if len(lines) == 1:
                lines.append("  (none)")
                 
        if direction in ("backward", "both"):
            lines.append(f"\nCaller Graph for {name} (Depth {depth}):")
            visited = set()
            def _walk_backward(curr, curr_depth, indent):
                if curr_depth > depth or curr in visited:
                     return
                visited.add(curr)
                callers = callers_map.get(curr, [])
                for caller in callers:
                    lines.append(f"{indent}<- {caller}")
                    _walk_backward(caller, curr_depth + 1, indent + "  ")
            _walk_backward(name, 1, "  ")
            if lines[-1].startswith("\nCaller"):
                lines.append("  (none)")
                 
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def execute(self, name: str, args: dict) -> str:
        args = args or {}
        if name == "read_file":
            return self.read_file(args.get("path", ""))
        if name == "list_files":
            return self.list_files(args.get("pattern", "*"))
        if name == "search_code":
            return self.search_code(args.get("query", ""), args.get("path", "."))
        if name == "get_mind_map":
            return self.get_mind_map()
        if name == "get_requirements":
            return self.get_requirements()
        if name == "get_diff":
            return self.get_diff(args.get("file_path"))
        if name == "get_function":
            return self.get_function(args.get("name", ""))
        if name == "get_call_graph":
            return self.get_call_graph(
                args.get("name", ""),
                depth=int(args.get("depth", 1)),
                direction=args.get("direction", "both")
            )
        raise ToolError(f"Unknown tool: {name}")

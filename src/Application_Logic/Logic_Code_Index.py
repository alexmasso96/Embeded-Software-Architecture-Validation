"""
Code Index — Universal C/C++ code analysis engine.

PORTED (Phase 7.5) — copied wholesale into this package from the standalone
`deep_code_indexer.py` reference tool. Per the project's critical constraint,
active code must NEVER import from the `Test Case Generator/` folder; this is the
in-package, version-controlled copy. It is stdlib-only (os, re, typing,
dataclasses) with no reach-back into any external module.

Public surface relied on by the mind-map builder (Logic_AI_Context):
  * build_index(sw_path) -> CodeIndex
  * CodeIndex.functions: Dict[name -> FunctionInfo]  (FunctionInfo.relpath is the
    file; .signature/.reads_vars/.writes_vars/.calls/.body/.conditions)
  * CodeIndex.globals: Dict[name -> GlobalVarInfo]   (note: 'globals', not 'global_vars')
  * CodeIndex.call_graph / reverse_call_graph: Dict[name -> List[name]]
  * CodeIndex.file_functions: Dict[relpath -> List[name]]
  * CodeIndex.find_functions_by_keywords(keywords, max_results) -> List[(name, score)]
  * extract_keywords(texts) -> List[str]  (public wrapper added during the port)

Project-agnostic: works with any C codebase (automotive, embedded, Linux, etc.)
by auto-detecting project patterns rather than hardcoding them.

Core capabilities:
  - Universal function definition extraction (handles any coding style)
  - Full call graph (caller → callee, both directions)
  - Struct/union member access chain tracking (a.b.c, a->b->c)
  - Condition extraction with full expressions
  - Global/static variable detection
  - #define and enum indexing
  - Comment stripping for accurate analysis
  - Data-flow: tracks assignments through variable chains

Optimized for speed on large codebases (1000+ files in <10s).
"""
import os
import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field


# ─── Configuration ───────────────────────────────────────────────────────────

SOURCE_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB

# Directories that never contain test-relevant source code
SKIP_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules",
    "bin", "obj", "build", "output", "out", "debug", "release",
    "polyspace", "misra", "lint", "doc", "docs", "documentation",
    "compiler_warnings", "toolcfg", "tools", "scripts",
    "ci-scripts", "architecture", "gitlab_config",
}

# C/C++ keywords - never function calls
C_KEYWORDS = {
    "if", "else", "while", "for", "do", "switch", "case", "default",
    "return", "break", "continue", "goto", "sizeof", "typeof", "defined",
    "struct", "union", "enum", "typedef", "extern", "static", "const",
    "volatile", "register", "inline", "void", "NULL", "TRUE", "FALSE",
    "true", "false", "nullptr", "class", "public", "private", "protected",
    "virtual", "override", "final", "template", "typename", "namespace",
    "using", "try", "catch", "throw", "new", "delete", "this",
    "auto", "decltype", "constexpr", "noexcept", "explicit",
    "asm", "__asm", "__attribute__", "__declspec",
}

# Common type names that appear in casts - not function calls
_BUILTIN_TYPES = {
    "u8", "u16", "u32", "u64", "s8", "s16", "s32", "s64",
    "U8", "U16", "U32", "U64", "S8", "S16", "S32", "S64",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "size_t", "ssize_t", "ptrdiff_t", "uintptr_t", "intptr_t",
    "boolean_t", "bool", "BOOL", "BOOLEAN",
    "float32", "float64", "float", "double", "int", "char", "long", "short",
    "unsigned", "signed", "void",
}


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class FunctionInfo:
    """Complete information about a C function."""
    name: str
    relpath: str = ""
    return_type: str = ""
    signature: str = ""
    params: List[Tuple[str, str]] = field(default_factory=list)
    body: str = ""
    line_start: int = 0
    line_end: int = 0
    is_static: bool = False
    # Analysis results
    calls: List[str] = field(default_factory=list)
    reads_vars: List[str] = field(default_factory=list)
    writes_vars: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    local_vars: List[Tuple[str, str]] = field(default_factory=list)
    switch_cases: List[str] = field(default_factory=list)
    assignments: List[str] = field(default_factory=list)


@dataclass
class GlobalVarInfo:
    """Global/module-scope variable."""
    name: str
    var_type: str
    relpath: str
    is_static: bool = False
    is_const: bool = False
    is_array: bool = False
    init_value: str = ""


class CodeIndex:
    """Complete code index for the software release."""

    def __init__(self):
        self.functions: Dict[str, FunctionInfo] = {}
        self.globals: Dict[str, GlobalVarInfo] = {}
        self.defines: Dict[str, str] = {}
        self.typedefs: Dict[str, str] = {}
        self.enums: Dict[str, List[str]] = {}  # enum_type -> [members]
        self.call_graph: Dict[str, List[str]] = {}  # caller -> [callees]
        self.reverse_call_graph: Dict[str, List[str]] = {}  # callee -> [callers]
        self.file_functions: Dict[str, List[str]] = {}  # relpath -> [func_names]
        self.file_globals: Dict[str, List[str]] = {}  # relpath -> [var_names]
        self.all_files: List[Dict] = []
        # Auto-detected project patterns
        self._known_types: Set[str] = set()  # Types discovered from typedefs/enums

    def get_callers(self, func_name: str) -> List[str]:
        return self.reverse_call_graph.get(func_name, [])

    def get_callees(self, func_name: str) -> List[str]:
        return self.call_graph.get(func_name, [])

    def get_call_chain_up(self, func_name: str, depth: int = 4) -> List[str]:
        """Trace callers upward: who calls this? who calls the caller?"""
        visited = set()
        chain = []

        def _walk(name, d):
            if d <= 0 or name in visited:
                return
            visited.add(name)
            for caller in self.get_callers(name):
                chain.append(f"{caller}() -> {name}()")
                _walk(caller, d - 1)

        _walk(func_name, depth)
        return chain

    def get_call_chain_down(self, func_name: str, depth: int = 3) -> List[str]:
        """Trace callees downward: what does this function call?"""
        visited = set()
        chain = []

        def _walk(name, d):
            if d <= 0 or name in visited:
                return
            visited.add(name)
            for callee in self.get_callees(name):
                chain.append(f"{name}() -> {callee}()")
                _walk(callee, d - 1)

        _walk(func_name, depth)
        return chain

    def trace_data_flow(self, var_pattern: str, max_depth: int = 3) -> List[Dict]:
        """
        Trace data flow for a variable across functions.
        
        Returns a list of data-flow entries:
          [{"var": "x", "writer_func": "A", "reader_funcs": ["B","C"],
            "write_condition": "if(y > TH)", "write_line": 123}]
        """
        pattern = var_pattern.lower()
        flow_entries = []
        
        # Find all writers of this variable
        writers = []
        for func in self.functions.values():
            for wvar in func.writes_vars:
                if pattern in wvar.lower():
                    writers.append((func, wvar))
                    break

        # For each writer, find readers
        for writer_func, full_var in writers:
            readers = []
            for func in self.functions.values():
                if func.name == writer_func.name:
                    continue
                for rvar in func.reads_vars:
                    if pattern in rvar.lower():
                        readers.append(func.name)
                        break

            # Find the condition under which the write happens
            write_cond = ""
            for cond in writer_func.conditions:
                if pattern in cond.lower():
                    write_cond = cond
                    break

            flow_entries.append({
                "var": full_var,
                "writer_func": writer_func.name,
                "writer_file": writer_func.relpath,
                "reader_funcs": readers[:8],
                "write_condition": write_cond,
            })

        return flow_entries[:15]

    def get_full_execution_path(self, func_name: str, depth_up: int = 5,
                                 depth_down: int = 4) -> Dict:
        """
        Get the complete execution path for a function:
        - Trace UP: Who calls this? Who calls the caller? (up to entry task)
        - Trace DOWN: What does this call? What do those call?
        
        Returns: {"up": [chain], "down": [chain], "siblings": [funcs at same level]}
        """
        # Trace upward to find entry point
        up_chain = []
        visited = set()
        
        def _walk_up(name, d):
            if d <= 0 or name in visited:
                return
            visited.add(name)
            callers = self.get_callers(name)
            for caller in callers[:3]:  # Limit branching
                up_chain.append(f"{caller}() → {name}()")
                _walk_up(caller, d - 1)
        
        _walk_up(func_name, depth_up)
        
        # Trace downward (what does this function call, recursively)
        down_chain = []
        visited2 = set()
        
        def _walk_down(name, d):
            if d <= 0 or name in visited2:
                return
            visited2.add(name)
            callees = self.get_callees(name)
            for callee in callees:
                if callee in self.functions:
                    down_chain.append(f"{name}() → {callee}()")
                    _walk_down(callee, d - 1)
        
        _walk_down(func_name, depth_down)
        
        # Find sibling functions (same file, same callers)
        siblings = []
        if func_name in self.functions:
            func = self.functions[func_name]
            file_funcs = self.file_functions.get(func.relpath, [])
            siblings = [f for f in file_funcs if f != func_name][:10]
        
        return {"up": up_chain, "down": down_chain, "siblings": siblings}

    def find_functions_by_keywords(self, keywords: List[str],
                                    max_results: int = 30) -> List[Tuple[int, 'FunctionInfo']]:
        """Score functions by keyword relevance. Returns [(score, func), ...]."""
        results = []
        kw_lower = [k.lower() for k in keywords if len(k) > 2]
        if not kw_lower:
            return results

        for func in self.functions.values():
            score = 0
            name_lower = func.name.lower()
            kw_hits = 0  # Track how many distinct keywords match

            # Name matching (highest weight)
            for kw in kw_lower:
                if kw in name_lower:
                    score += 12
                    kw_hits += 1
                    if name_lower.startswith(kw) or name_lower.endswith(kw):
                        score += 5
                    # Exact CamelCase component match
                    parts = re.findall(r'[A-Z][a-z]+|[a-z]+', func.name)
                    if kw in [p.lower() for p in parts]:
                        score += 4

            # Variable access matching (second highest)
            all_vars_text = " ".join(func.reads_vars + func.writes_vars).lower()
            for kw in kw_lower:
                if kw in all_vars_text:
                    score += 6
                    kw_hits += 1

            # Condition matching (very important - shows decision logic)
            cond_text = " ".join(func.conditions).lower()
            for kw in kw_lower:
                if kw in cond_text:
                    score += 5
                    kw_hits += 1

            # Assignment matching (shows data-flow)
            assign_text = " ".join(func.assignments).lower()
            if score > 0:
                for kw in kw_lower:
                    if kw in assign_text:
                        score += 3

            # Body text matching (for all functions, not just already-scoring)
            body_lower = func.body.lower() if len(func.body) < 50000 else ""
            if body_lower:
                body_hits = 0
                for kw in kw_lower:
                    if kw in body_lower:
                        body_hits += 1
                if body_hits > 0:
                    # Scale body score: more keyword hits = more relevant
                    score += body_hits * 2
                    kw_hits += body_hits

            # File path matching (helps group related code)
            if score > 0:
                path_lower = func.relpath.lower()
                for kw in kw_lower:
                    if kw in path_lower:
                        score += 3

            # Bonus: multiple distinct keyword matches = much more relevant
            if kw_hits >= 3:
                score += kw_hits * 3
            elif kw_hits >= 2:
                score += kw_hits * 2

            # Bonus: functions with many conditions are likely decision points
            if score > 0 and len(func.conditions) >= 2:
                score += 2

            if score > 0:
                results.append((score, func))

        results.sort(key=lambda x: x[0], reverse=True)
        return results[:max_results]

    def find_functions_accessing_variable(self, var_pattern: str) -> List[FunctionInfo]:
        """Find all functions that read or write a variable matching the pattern."""
        pattern = var_pattern.lower()
        results = []
        for func in self.functions.values():
            all_vars = func.reads_vars + func.writes_vars
            for v in all_vars:
                if pattern in v.lower():
                    results.append(func)
                    break
        return results

    def find_related_globals(self, keywords: List[str]) -> List[GlobalVarInfo]:
        """Find global variables matching keywords."""
        kw_lower = [k.lower() for k in keywords if len(k) > 2]
        results = []
        for var in self.globals.values():
            name_lower = var.name.lower()
            type_lower = var.var_type.lower()
            for kw in kw_lower:
                if kw in name_lower or kw in type_lower:
                    results.append(var)
                    break
        return results

    def find_related_defines(self, keywords: List[str]) -> List[Tuple[str, str]]:
        """Find #defines matching keywords."""
        kw_lower = [k.lower() for k in keywords if len(k) > 2]
        results = []
        for name, value in self.defines.items():
            name_lower = name.lower()
            for kw in kw_lower:
                if kw in name_lower:
                    results.append((name, value))
                    break
        return results

    def find_related_enums(self, keywords: List[str]) -> List[Tuple[str, List[str]]]:
        """Find enum types matching keywords."""
        kw_lower = [k.lower() for k in keywords if len(k) > 2]
        results = []
        for enum_name, members in self.enums.items():
            all_text = (enum_name + ' ' + ' '.join(members)).lower()
            for kw in kw_lower:
                if kw in all_text:
                    results.append((enum_name, members))
                    break
        return results


# ─── Comment Stripping ───────────────────────────────────────────────────────

def _strip_comments(content: str) -> str:
    """Remove C/C++ comments while preserving line structure (for accurate line numbers).
    Uses regex-based approach for speed on large files."""
    # Fast regex approach: handles most cases correctly
    # Pattern matches: strings (to skip them), line comments, block comments
    _comment_re = re.compile(
        r'("(?:[^"\\]|\\.)*"'       # double-quoted strings (group 1)
        r"|'(?:[^'\\]|\\.)*'"       # single-quoted chars
        r')|//[^\n]*'               # line comments
        r'|/\*.*?\*/',              # block comments
        re.DOTALL
    )

    def _replacer(m):
        if m.group(1):  # It's a string literal - keep it
            return m.group(0)
        # It's a comment - replace with spaces but keep newlines
        return re.sub(r'[^\n]', ' ', m.group(0))

    return _comment_re.sub(_replacer, content)


# ─── File Scanning ───────────────────────────────────────────────────────────

def _scan_files(sw_path: str) -> List[Dict]:
    """Recursively scan for C/C++ source files."""
    files = []
    for root, dirs, filenames in os.walk(sw_path):
        # Skip irrelevant directories
        basename = os.path.basename(root).lower()
        if basename in SKIP_DIRS:
            dirs.clear()
            continue

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SOURCE_EXTENSIONS:
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                    if size <= MAX_FILE_SIZE and size > 0:
                        files.append({
                            "path": fpath,
                            "relpath": os.path.relpath(fpath, sw_path),
                            "name": fname,
                            "size": size,
                            "ext": ext,
                        })
                except OSError:
                    continue
    return files


# ─── Function Extraction ─────────────────────────────────────────────────────

# Universal C function definition regex.
# Matches virtually any C function definition pattern:
#   void main(void)
#   static int calculate_value(int x, float y)
#   myType_t* MyModule_GetStatus(const myParam_t *param)
#   unsigned long long compute(void)
# Does NOT match: if(), while(), for(), macros, typedefs
_TYPE_QUALIFIER_RE = r'(?:(?:static|inline|extern|const|volatile|__attribute__\s*\([^)]*\))\s+)*'
_RETURN_TYPE_RE = (
    r'(?:(?:const|volatile|unsigned|signed|long|short|struct|union|enum)\s+)*'
    r'(?:[A-Za-z_]\w*)'
    r'(?:\s*\*\s*)*'
)


def _is_type_keyword(word: str) -> bool:
    """Check if a word is a type name (built-in or common pattern)."""
    if word in _BUILTIN_TYPES:
        return True
    # Common patterns: ends with _t, _st, _type, Type
    if re.match(r'^\w+(_t|_st|_type|Type|TYPE)$', word):
        return True
    return False


def _extract_functions(content: str, relpath: str, known_types: Set[str]) -> List[FunctionInfo]:
    """
    Extract all function definitions with their full bodies.
    
    Uses a state-machine approach rather than a single regex, which handles:
    - Multi-line signatures
    - Complex return types (struct pointers, unsigned long long, etc.)
    - Trailing annotations (polyspace, PRQA, GCC attributes)
    - Rhapsody markers
    """
    functions = []
    # Work on comment-stripped content for accuracy
    stripped_content = _strip_comments(content)
    lines = stripped_content.split('\n')
    orig_lines = content.split('\n')  # Keep originals for body extraction
    n_lines = len(lines)

    # Pre-compile patterns
    # Matches: [qualifiers] type name(params) possibly followed by { on same or next lines
    func_start_re = re.compile(
        r'^(?P<prefix>(?:(?:static|inline|extern|const|volatile|__inline|__forceinline)\s+)*)'
        r'(?P<rettype>'
        r'(?:(?:const|volatile|unsigned|signed|long|short|struct|union|enum)\s+)*'
        r'[A-Za-z_]\w*'
        r'(?:\s*\*+\s*)?'
        r')\s+'
        r'(?P<funcname>[A-Za-z_]\w*)\s*'
        r'\((?P<params>[^)]*)\)\s*$'
    )

    # Alternative: params on next line or type on prev line
    partial_func_re = re.compile(
        r'^(?P<prefix>(?:(?:static|inline|extern|const|volatile)\s+)*)'
        r'(?P<rettype>'
        r'(?:(?:const|volatile|unsigned|signed|long|short|struct|union|enum)\s+)*'
        r'[A-Za-z_]\w*'
        r'(?:\s*\*+\s*)?'
        r')\s+'
        r'(?P<funcname>[A-Za-z_]\w*)\s*'
        r'\((?P<params>[^)]*$)'  # Open paren but no close
    )

    i = 0
    while i < n_lines:
        stripped = lines[i].strip()

        # Skip empty, preprocessor, leftover whitespace from stripped comments
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        # Try single-line match
        match = func_start_re.match(stripped)

        if not match:
            # Try multi-line: return type on one line, name(params) on next
            if i + 1 < n_lines and not stripped.endswith('{') and not stripped.endswith(';'):
                next_stripped = lines[i + 1].strip()
                combined = stripped + ' ' + next_stripped
                match = func_start_re.match(combined)
                if match:
                    i += 1  # consumed next line

        if not match and not stripped.endswith(';') and not stripped.endswith('{'):
            # Try partial (multi-line params)
            partial = partial_func_re.match(stripped)
            if partial:
                # Accumulate lines until we find the closing paren
                combined = stripped
                j = i + 1
                while j < min(i + 5, n_lines):
                    combined += ' ' + lines[j].strip()
                    if ')' in lines[j]:
                        break
                    j += 1
                # Try matching the combined
                match = func_start_re.match(combined)
                if match:
                    i = j

        if match:
            prefix = match.group('prefix').strip()
            is_static = 'static' in prefix
            ret_type = match.group('rettype').strip()
            func_name = match.group('funcname')
            params_str = match.group('params').strip()

            # Filter out false positives
            if func_name in C_KEYWORDS or func_name in _BUILTIN_TYPES:
                i += 1
                continue
            # Skip if it looks like a macro invocation (all caps and short)
            if func_name.isupper() and len(func_name) < 5:
                i += 1
                continue

            # Find the opening brace (must be within next few lines)
            brace_found = False
            brace_line = i
            search_end = min(i + 8, n_lines)

            for j in range(i, search_end):
                if '{' in lines[j]:
                    brace_line = j
                    brace_found = True
                    break
                # If we hit ; without { it's a prototype/declaration
                if lines[j].strip().endswith(';') and '{' not in lines[j]:
                    break

            if not brace_found:
                i += 1
                continue

            # Find matching closing brace (brace counting)
            depth = 0
            body_end = brace_line

            for j in range(brace_line, min(brace_line + 5000, n_lines)):
                line_text = lines[j]
                for ch in line_text:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            body_end = j
                            break
                if depth == 0 and j > brace_line:
                    break

            if depth != 0:
                i += 1
                continue

            # Extract body from ORIGINAL (with comments) for display
            body = '\n'.join(orig_lines[brace_line:body_end + 1])
            # Use stripped version for analysis
            analysis_body = '\n'.join(lines[brace_line:body_end + 1])

            # Build function info
            func = FunctionInfo(name=func_name)
            func.relpath = relpath
            func.return_type = ret_type
            func.is_static = is_static
            func.signature = f"{ret_type} {func_name}({params_str})"
            func.params = _parse_params(params_str)
            func.body = body
            func.line_start = i + 1  # 1-indexed (approximate)
            func.line_end = body_end + 1

            # Deep analysis of function body (use comment-stripped version)
            _analyze_function_body(func, analysis_body, known_types)

            functions.append(func)
            i = body_end + 1
        else:
            i += 1

    return functions


def _parse_params(params_str: str) -> List[Tuple[str, str]]:
    """Parse function parameters into (type, name) tuples."""
    params = []
    if not params_str or params_str.strip().lower() == "void":
        return params

    for p in params_str.split(","):
        p = p.strip()
        if not p or p.lower() == "void":
            continue
        # Split: everything except last word is type, last word is name
        parts = p.rsplit(None, 1)
        if len(parts) == 2:
            ptype = parts[0].strip()
            pname = parts[1].strip().lstrip('*')
            params.append((ptype, pname))
        elif parts:
            params.append(("", parts[0].strip()))
    return params


# ─── Function Body Analysis ──────────────────────────────────────────────────

def _analyze_function_body(func: FunctionInfo, body: str, known_types: Set[str]):
    """Deep analysis of function body: calls, variables, conditions, data flow."""
    param_names = {p[1] for p in func.params if p[1]}

    # Extract local variable declarations
    func.local_vars = _extract_locals(body)
    local_names = {lv[1] for lv in func.local_vars}

    # All identifiers that are "own" (parameter or local)
    own_vars = param_names | local_names

    # Extract function calls
    func.calls = _extract_calls(body, func.name, known_types)

    # Extract conditions (if, while, for comparisons)
    func.conditions = _extract_conditions(body)

    # Extract switch cases
    func.switch_cases = _extract_switch_cases(body)

    # Extract variable reads/writes and assignments
    func.reads_vars, func.writes_vars, func.assignments = _extract_var_accesses(body, own_vars)


def _extract_locals(body: str) -> List[Tuple[str, str]]:
    """Extract local variable declarations from function body."""
    locals_found = []
    # Match local variable declarations (indented lines with type + name)
    # Handles: int x; const float y = 3.0; myType_t *ptr; u8 buffer[10];
    local_re = re.compile(
        r'^\s+'  # Must be indented (inside function)
        r'(?:const\s+|volatile\s+|static\s+)?'
        r'((?:unsigned\s+|signed\s+|long\s+|short\s+|struct\s+|enum\s+)?'
        r'[A-Za-z_]\w*'
        r'(?:\s*\*)*)\s+'
        r'(\w+)\s*'
        r'(?:\[[^\]]*\])?\s*'  # Optional array subscript
        r'(?:=[^;]*)?\s*;',
        re.MULTILINE
    )
    for m in local_re.finditer(body):
        var_type = m.group(1).strip()
        var_name = m.group(2).strip()
        # Filter: skip if type is a keyword used as prefix for next word
        if var_name and var_name not in C_KEYWORDS and not var_name.startswith('__'):
            locals_found.append((var_type, var_name))
    return locals_found


def _extract_calls(body: str, self_name: str, known_types: Set[str]) -> List[str]:
    """Extract all function calls from body (excludes casts, keywords, macros)."""
    calls = set()
    call_re = re.compile(r'\b([A-Za-z_]\w*)\s*\(')

    for m in call_re.finditer(body):
        name = m.group(1)
        # Skip keywords
        if name in C_KEYWORDS:
            continue
        # Skip self-recursion
        if name == self_name:
            continue
        # Skip type casts
        if name in _BUILTIN_TYPES or name in known_types:
            continue
        # Skip common assertion/logging macros that aren't function calls
        if name.startswith('__') or (name.isupper() and '_' in name and len(name) < 6):
            continue
        calls.add(name)

    return sorted(calls)


def _extract_conditions(body: str) -> List[str]:
    """Extract if/while/for conditions with full expressions."""
    conditions = []
    cond_re = re.compile(r'\b(?:if|while|for)\s*\(')

    for m in cond_re.finditer(body):
        start = m.end() - 1  # Position of opening (
        # Find matching closing )
        depth = 0
        end = start
        for k in range(start, min(start + 600, len(body))):
            if body[k] == '(':
                depth += 1
            elif body[k] == ')':
                depth -= 1
                if depth == 0:
                    end = k
                    break

        if end > start:
            cond_text = body[start + 1:end].strip()
            cond_text = re.sub(r'\s+', ' ', cond_text)
            # Skip trivial or overly long conditions
            if 4 < len(cond_text) < 400:
                conditions.append(cond_text)

    return conditions


def _extract_switch_cases(body: str) -> List[str]:
    """Extract switch case values."""
    cases = []
    case_re = re.compile(r'\bcase\s+([\w]+)\s*:')
    for m in case_re.finditer(body):
        cases.append(m.group(1))
    return cases


def _extract_var_accesses(body: str, own_vars: Set[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    Extract variable accesses (reads and writes) that are NOT local/param.
    
    Tracks:
    - Full struct access paths: obj.member.field, ptr->member->field
    - Array accesses: array[idx].member
    - Simple globals (identifiers not in own_vars and not function calls)
    
    Returns: (reads, writes, assignments)
    """
    reads = set()
    writes = set()
    assignments = []

    # Pattern for access chains: identifier followed by .member, ->member, [idx]
    access_chain_re = re.compile(
        r'\b([A-Za-z_]\w*'
        r'(?:\s*(?:\.\s*[A-Za-z_]\w*|\->\s*[A-Za-z_]\w*|\[\s*[^\]]+\s*\]))+)'
    )

    # Pattern for simple variable (not followed by open paren = not a call)
    simple_var_re = re.compile(r'\b([A-Za-z_]\w*)\b')

    for line in body.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Find the assignment operator (first = that isn't ==, !=, <=, >=, +=, -=, etc.)
        # For compound assignments (+=, -=, etc.) the LHS is both read and write
        eq_pos = -1
        compound = False
        for idx in range(len(stripped)):
            ch = stripped[idx]
            if ch == '=' and idx + 1 < len(stripped) and stripped[idx + 1] != '=':
                # Check it's not !=, <=, >=
                if idx > 0 and stripped[idx - 1] in ('!', '<', '>', '+', '-', '*', '/', '%', '&', '|', '^'):
                    if stripped[idx - 1] in ('+', '-', '*', '/', '%', '&', '|', '^'):
                        compound = True
                        eq_pos = idx - 1
                    continue
                eq_pos = idx
                break

        # Track full assignment for data-flow
        if eq_pos > 0:
            lhs = stripped[:eq_pos].strip().rstrip('+-*/%&|^')
            rhs = stripped[eq_pos:].lstrip('=').strip().rstrip(';')
            if lhs and rhs and len(lhs) < 150 and len(rhs) < 200:
                assignments.append(f"{lhs} = {rhs}")

        # Find access chains (struct.member.field, ptr->member)
        for m in access_chain_re.finditer(stripped):
            path = re.sub(r'\s+', '', m.group(1))
            root = path.split('.')[0].split('[')[0].split('-')[0]

            if root in own_vars or root in C_KEYWORDS:
                continue
            # Skip if followed by ( — it's a method/function call result
            pos_after = m.end()
            if pos_after < len(stripped) and stripped[pos_after:pos_after + 1] == '(':
                continue

            if eq_pos > 0 and m.start() < eq_pos:
                writes.add(path)
                if compound:
                    reads.add(path)
            else:
                reads.add(path)

        # Find simple global references (not in a chain, not a call)
        for m in simple_var_re.finditer(stripped):
            name = m.group(1)
            if name in own_vars or name in C_KEYWORDS or name in _BUILTIN_TYPES:
                continue
            # Skip if it's part of an access chain we already captured
            # (check if preceded by . or ->)
            pos_before = m.start()
            if pos_before > 0 and stripped[pos_before - 1] in ('.', '>'):
                continue
            # Skip if followed by ( — it's a function call
            pos_after = m.end()
            if pos_after < len(stripped) and stripped[pos_after:pos_after + 1] == '(':
                continue
            # Skip pure numbers, single chars, likely macros
            if name.isupper() and len(name) <= 3:
                continue
            # Skip if it's the type in a declaration (heuristic: at start of line before another ident)
            if m.start() == 0 or stripped[:m.start()].strip() == '':
                # Could be a declaration - skip
                continue

            # This looks like a global/module-scope variable reference
            if eq_pos > 0 and m.start() < eq_pos:
                writes.add(name)
                if compound:
                    reads.add(name)
            elif eq_pos != 0:  # Don't add LHS as read when it's pure assignment target
                reads.add(name)

    return sorted(reads)[:40], sorted(writes)[:25], assignments[:20]


# ─── Global Variable Extraction ──────────────────────────────────────────────

def _extract_globals(content: str, relpath: str) -> List[GlobalVarInfo]:
    """Extract module-scope and extern variable declarations."""
    globals_found = []

    # Universal pattern for file-scope variables
    global_re = re.compile(
        r'^(?P<quals>(?:(?:static|extern|const|volatile)\s+)*)'
        r'(?P<type>'
        r'(?:(?:unsigned|signed|long|short|struct|union|enum)\s+)*'
        r'[A-Za-z_]\w*'
        r'(?:\s*\*)*)\s+'
        r'(?P<name>[A-Za-z_]\w*)\s*'
        r'(?P<array>\[[^\]]*\])?\s*'
        r'(?:=\s*(?P<init>[^;]{1,150}))?\s*;',
        re.MULTILINE
    )

    for m in global_re.finditer(content):
        # Verify at file scope: check indentation (must be <=4 spaces from line start)
        line_start = content.rfind('\n', 0, m.start()) + 1
        indent = m.start() - line_start
        if indent > 4:
            continue

        name = m.group('name')
        quals = m.group('quals').strip()
        var_type = m.group('type').strip()

        # Skip function prototypes (has paren after match)
        after = content[m.end():m.end() + 3]
        if '(' in after:
            continue
        # Skip keywords that slipped through
        if name in C_KEYWORDS or name in _BUILTIN_TYPES:
            continue

        gvar = GlobalVarInfo(
            name=name,
            var_type=var_type,
            relpath=relpath,
            is_static='static' in quals,
            is_const='const' in quals,
            is_array=m.group('array') is not None,
            init_value=m.group('init').strip() if m.group('init') else "",
        )
        globals_found.append(gvar)

    return globals_found


# ─── #define / Enum / Typedef Extraction ─────────────────────────────────────

def _extract_defines(content: str) -> Dict[str, str]:
    """Extract #define macros with their values."""
    defines = {}
    define_re = re.compile(
        r'^\s*#\s*define\s+(\w+)(?:\([^)]*\))?\s*(.*?)$',
        re.MULTILINE
    )
    for m in define_re.finditer(content):
        name = m.group(1)
        value = m.group(2).strip()
        # Strip trailing comments
        if '/*' in value:
            value = value[:value.index('/*')].strip()
        if '//' in value:
            value = value[:value.index('//')].strip()
        # Remove line continuations for multi-line macros
        value = value.rstrip('\\').strip()
        # Skip include guards
        if name.startswith('_') and (name.endswith('_H') or name.endswith('_H_')):
            continue
        # Skip overly complex macro bodies
        if len(value) <= 200:
            defines[name] = value
    return defines


def _extract_enums(content: str) -> Tuple[Dict[str, List[str]], Set[str]]:
    """Extract enum types and return both enums and discovered type names."""
    enums = {}
    types = set()

    # typedef enum { ... } name;
    enum_re = re.compile(
        r'typedef\s+enum\s*(?:\w*\s*)?\{([^}]+)\}\s*(\w+)\s*;',
        re.DOTALL
    )
    for m in enum_re.finditer(content):
        body = m.group(1)
        enum_name = m.group(2)
        types.add(enum_name)
        members = []
        for member_m in re.finditer(r'(\w+)\s*(?:=\s*[^,}]+)?\s*[,}]', body):
            member = member_m.group(1)
            if member not in C_KEYWORDS:
                members.append(member)
        if members:
            enums[enum_name] = members

    return enums, types


def _extract_typedefs(content: str) -> Set[str]:
    """Extract typedef names to know what's a type vs a variable/function."""
    types = set()
    # typedef ... name;
    typedef_re = re.compile(r'typedef\s+[^;]+\s+(\w+)\s*;')
    for m in typedef_re.finditer(content):
        types.add(m.group(1))
    # Also struct/union typedefs
    struct_re = re.compile(r'typedef\s+(?:struct|union)\s*\w*\s*\{[^}]*\}\s*(\w+)\s*;', re.DOTALL)
    for m in struct_re.finditer(content):
        types.add(m.group(1))
    return types


# ─── Build Index ─────────────────────────────────────────────────────────────

def build_index(sw_path: str) -> CodeIndex:
    """
    Build a complete code index for any C/C++ software project.
    
    Two-pass approach:
      Pass 1: Headers → extract types, defines, enums, extern globals
      Pass 2: Sources → extract functions, module statics, build call graph
    """
    index = CodeIndex()
    index.all_files = _scan_files(sw_path)

    # Pass 1: Headers - discover types, defines, enums
    for finfo in index.all_files:
        if finfo["ext"] not in (".h", ".hpp", ".hh"):
            continue
        try:
            with open(finfo["path"], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Extract defines
            defines = _extract_defines(content)
            index.defines.update(defines)

            # Extract enums and discover types
            enums, enum_types = _extract_enums(content)
            index.enums.update(enums)
            index._known_types.update(enum_types)

            # Extract typedefs (to know what's a type for call detection)
            td_types = _extract_typedefs(content)
            index._known_types.update(td_types)

            # Extract extern/global declarations
            gvars = _extract_globals(content, finfo["relpath"])
            for gv in gvars:
                index.globals[gv.name] = gv
                if finfo["relpath"] not in index.file_globals:
                    index.file_globals[finfo["relpath"]] = []
                index.file_globals[finfo["relpath"]].append(gv.name)

        except (IOError, OSError):
            continue

    # Pass 2: Source files - extract functions, call graph, module-scope statics
    for finfo in index.all_files:
        if finfo["ext"] not in (".c", ".cpp", ".cc", ".cxx"):
            continue
        try:
            with open(finfo["path"], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Extract defines from source files too
            defines = _extract_defines(content)
            index.defines.update(defines)

            # Discover more types
            td_types = _extract_typedefs(content)
            index._known_types.update(td_types)
            enums, enum_types = _extract_enums(content)
            index.enums.update(enums)
            index._known_types.update(enum_types)

            # Extract module-scope variables
            gvars = _extract_globals(content, finfo["relpath"])
            for gv in gvars:
                index.globals[gv.name] = gv
                if finfo["relpath"] not in index.file_globals:
                    index.file_globals[finfo["relpath"]] = []
                index.file_globals[finfo["relpath"]].append(gv.name)

            # Extract functions (pass known types to avoid false call detection)
            funcs = _extract_functions(content, finfo["relpath"], index._known_types)
            for func in funcs:
                index.functions[func.name] = func
                # Build call graph
                index.call_graph[func.name] = func.calls
                for callee in func.calls:
                    if callee not in index.reverse_call_graph:
                        index.reverse_call_graph[callee] = []
                    if func.name not in index.reverse_call_graph[callee]:
                        index.reverse_call_graph[callee].append(func.name)
                # Track file→functions mapping
                if finfo["relpath"] not in index.file_functions:
                    index.file_functions[finfo["relpath"]] = []
                index.file_functions[finfo["relpath"]].append(func.name)

        except (IOError, OSError):
            continue

    return index


# ─── Requirement Tracing ─────────────────────────────────────────────────────

def trace_requirement(index: CodeIndex, requirement_text: str,
                      max_context_chars: int = 25000) -> str:
    """
    Trace a requirement/TCD through the code to find implementing functions.

    Deep analysis approach:
    1. Find top-scoring functions by keyword matching
    2. For each, trace the COMPLETE execution path (up to entry + down to leaves)
    3. Include cross-function DATA FLOW (who writes variable X → who reads it)
    4. Present ALL related code with conditions, thresholds, and state transitions
    5. Include sibling functions from same file (often part of same module logic)

    Returns structured code context string for the AI prompt.
    """
    keywords = _extract_keywords(requirement_text)

    # Find matching functions with improved scoring
    scored_funcs = index.find_functions_by_keywords(keywords)
    if not scored_funcs:
        return (f"[NO MATCHING FUNCTIONS FOUND]\n"
                f"Keywords searched: {', '.join(keywords[:15])}\n"
                f"Total functions in index: {len(index.functions)}\n"
                f"Hint: Try more specific function/variable names from the source code.")

    # Determine the primary implementing functions (top 8)
    primary_funcs = [f for _, f in scored_funcs[:8]]

    # Collect the full execution tree with DEEP tracing
    execution_tree_funcs = set()
    for func in primary_funcs:
        execution_tree_funcs.add(func.name)
        # Add ALL callees (functions called by the primary function) - 2 levels deep
        for callee in func.calls:
            if callee in index.functions:
                execution_tree_funcs.add(callee)
                # Second level callees (critical for understanding full logic)
                callee_func = index.functions[callee]
                for sub_callee in callee_func.calls[:6]:
                    if sub_callee in index.functions:
                        execution_tree_funcs.add(sub_callee)
        # Add callers (who triggers this function) - 3 levels up
        for caller in index.get_callers(func.name):
            execution_tree_funcs.add(caller)
            for grandcaller in index.get_callers(caller):
                execution_tree_funcs.add(grandcaller)

    # Build structured context
    parts = []
    parts.append(f"[CODE INDEX: {len(index.functions)} functions, "
                 f"{len(index.globals)} globals, {len(index.defines)} defines, "
                 f"{len(index.enums)} enums from {len(index.all_files)} files]")
    parts.append(f"[Keywords matched: {', '.join(keywords[:12])}]")
    parts.append(f"[Primary functions: {', '.join(f.name for f in primary_funcs)}]")
    parts.append(f"[Execution tree: {len(execution_tree_funcs)} related functions]\n")

    total_size = 0

    # ═══ Section 1: EXECUTION FLOW MAP (critical for understanding code logic) ═══
    parts.append("/* ══════ COMPLETE EXECUTION FLOW MAP ══════ */")
    parts.append("/* Shows the full call chain from entry points to leaf functions */")
    for func in primary_funcs[:6]:
        exec_path = index.get_full_execution_path(func.name, depth_up=5, depth_down=4)
        if exec_path["up"] or exec_path["down"]:
            parts.append(f"\n/* Flow for {func.name}(): */")
            if exec_path["up"]:
                parts.append(f"/*   ENTRY PATH (who triggers this): */")
                for chain_link in exec_path["up"][:6]:
                    parts.append(f"/*     {chain_link} */")
            if exec_path["down"]:
                parts.append(f"/*   CALLED (what this invokes): */")
                for chain_link in exec_path["down"][:8]:
                    parts.append(f"/*     {chain_link} */")
            if exec_path["siblings"]:
                parts.append(f"/*   SAME MODULE: {', '.join(exec_path['siblings'][:6])} */")
    parts.append("")
    total_size += sum(len(p) for p in parts)

    # ═══ Section 2: DATA FLOW ANALYSIS ═══
    # Trace how key variables flow between functions
    data_flow_section = []
    traced_vars = set()
    for func in primary_funcs[:4]:
        for wvar in func.writes_vars[:5]:
            var_root = wvar.split('.')[0].split('[')[0].split('-')[0]
            if var_root in traced_vars or len(var_root) < 4:
                continue
            traced_vars.add(var_root)
            flow = index.trace_data_flow(var_root)
            if flow:
                for entry in flow[:3]:
                    readers_str = ', '.join(entry['reader_funcs'][:5])
                    data_flow_section.append(
                        f"/*   {entry['var']}: "
                        f"written by {entry['writer_func']}() "
                        f"→ read by [{readers_str}]"
                        f"{' when: ' + entry['write_condition'] if entry['write_condition'] else ''}"
                        f" */")

    if data_flow_section and total_size < max_context_chars - 2000:
        parts.append("/* ══════ CROSS-FUNCTION DATA FLOW ══════ */")
        parts.append("/* Shows how variables flow between functions (write → read chains) */")
        parts.extend(data_flow_section[:20])
        parts.append("")
        total_size += sum(len(p) for p in data_flow_section)

    # ═══ Section 3: Related #defines (thresholds, config values) ═══
    related_defines = index.find_related_defines(keywords)
    if related_defines:
        parts.append("/* ══════ THRESHOLDS & CONFIGURATION DEFINES ══════ */")
        for name, value in related_defines[:35]:
            line = f"#define {name}  {value}"
            parts.append(line)
            total_size += len(line)
        parts.append("")

    # ═══ Section 4: Related global/module variables ═══
    related_globals = index.find_related_globals(keywords)
    if related_globals:
        parts.append("/* ══════ GLOBAL/MODULE VARIABLES ══════ */")
        for gv in related_globals[:20]:
            qualifiers = []
            if gv.is_static:
                qualifiers.append("static")
            if gv.is_const:
                qualifiers.append("const")
            qual_str = ' '.join(qualifiers) + ' ' if qualifiers else ''
            array_kw = "[]" if gv.is_array else ""
            init = f" = {gv.init_value}" if gv.init_value else ""
            line = f"{qual_str}{gv.var_type} {gv.name}{array_kw}{init};  /* {gv.relpath} */"
            parts.append(line)
            total_size += len(line)
        parts.append("")

    # ═══ Section 5: Related enums ═══
    related_enums = index.find_related_enums(keywords)
    if related_enums and total_size < max_context_chars - 500:
        parts.append("/* ══════ RELATED ENUM TYPES ══════ */")
        for enum_name, members in related_enums[:8]:
            members_str = ', '.join(members[:20])
            if len(members) > 20:
                members_str += f", ... ({len(members)} total)"
            parts.append(f"typedef enum {{ {members_str} }} {enum_name};")
            total_size += len(members_str) + 30
        parts.append("")

    # ═══ Section 6: FULL EXECUTION FLOW - Complete Function Bodies ═══
    parts.append("/* ══════════════════════════════════════════════════════════ */")
    parts.append("/* ══════ FULL CODE BODIES (for test step generation) ══════ */")
    parts.append("/* ══════════════════════════════════════════════════════════ */")
    parts.append("/*")
    parts.append(" * COMPLETE source code bodies presented in execution order:")
    parts.append(" * 1. ENTRY POINTS - task/cyclic functions that start the flow")
    parts.append(" * 2. PRIMARY FUNCTIONS - decision logic implementing the requirement")
    parts.append(" * 3. CALLED FUNCTIONS - subfunctions for specific operations")
    parts.append(" * Use line numbers for breakpoint locations in test steps.")
    parts.append(" */\n")

    # --- 6a: Entry points (callers of primary functions) ---
    included_funcs = set()
    parts.append("/* ── ENTRY POINTS (callers that trigger the requirement logic) ── */")
    for func in primary_funcs[:5]:
        callers = index.get_callers(func.name)
        if callers and total_size < max_context_chars - 2000:
            for caller_name in callers[:3]:
                if caller_name in index.functions and caller_name not in included_funcs:
                    caller = index.functions[caller_name]
                    included_funcs.add(caller_name)
                    caller_block = _format_function_block(caller, "ENTRY POINT", index)
                    # Limit entry point bodies to save space for primary functions
                    if total_size + len(caller_block) > max_context_chars * 0.25:
                        caller_block = (
                            f"\n/* ENTRY POINT: {caller.relpath} line {caller.line_start}-{caller.line_end} */\n"
                            f"/* Calls: {', '.join(caller.calls[:12])} */\n"
                            f"/* Conditions: {'; '.join(caller.conditions[:4])} */\n"
                            f"{caller.signature};\n"
                        )
                    parts.append(caller_block)
                    total_size += len(caller_block)
    parts.append("")

    # --- 6b: Primary implementing functions (FULL bodies, ALWAYS included) ---
    parts.append("/* ── PRIMARY IMPLEMENTING FUNCTIONS (contain the decision logic) ── */")
    for func in primary_funcs:
        if total_size > max_context_chars * 0.85:
            # Even at budget limit, include at least the metadata + conditions
            if func.name not in included_funcs:
                included_funcs.add(func.name)
                header = _format_function_header(func, "IMPLEMENTS REQUIREMENT", index)
                parts.append(header + f"{func.signature}; /* body truncated - {len(func.body)} chars */\n")
                total_size += len(header) + 80
            continue
        if func.name in included_funcs:
            continue
        included_funcs.add(func.name)

        func_block = _format_function_block(func, "IMPLEMENTS REQUIREMENT", index)

        # If body is too large, truncate smartly but keep all conditions
        body_size = len(func.body)
        if total_size + len(func_block) > max_context_chars * 0.7:
            available = int((max_context_chars * 0.7) - total_size - 500)
            if available > 800:
                body_lines = func.body.split('\n')
                max_lines = max(available // 50, 20)
                truncated_body = '\n'.join(body_lines[:max_lines])
                func_block = _format_function_header(func, "IMPLEMENTS REQUIREMENT", index)
                func_block += f"{func.signature}\n{truncated_body}\n/* ... ({len(body_lines)} lines total) */\n"
            else:
                func_block = _format_function_header(func, "IMPLEMENTS REQUIREMENT", index)
                func_block += f"{func.signature}; /* {body_size} chars - see conditions above */\n"

        parts.append(func_block)
        total_size += len(func_block)
    parts.append("")

    # --- 6c: Called functions (what the primary functions invoke) ---
    parts.append("/* ── CALLED FUNCTIONS (invoked by the primary functions) ── */")
    for func in primary_funcs[:5]:
        for callee_name in func.calls[:10]:
            if callee_name in index.functions and callee_name not in included_funcs:
                if total_size > max_context_chars * 0.95:
                    break
                callee = index.functions[callee_name]
                included_funcs.add(callee_name)

                # Score callee by keyword relevance
                callee_text = (callee.name + ' ' + ' '.join(callee.reads_vars + callee.writes_vars + callee.conditions)).lower()
                callee_relevant = False
                for kw in keywords[:10]:
                    if kw.lower() in callee_text:
                        callee_relevant = True
                        break

                if callee_relevant:
                    callee_block = _format_function_block(callee, f"CALLED BY {func.name}()", index)
                    if total_size + len(callee_block) > max_context_chars:
                        callee_block = _format_function_header(callee, f"CALLED BY {func.name}()", index)
                        callee_block += f"{callee.signature};\n"
                    parts.append(callee_block)
                    total_size += len(callee_block)
                else:
                    # Include minimal info for non-keyword-matching callees
                    # (still valuable for understanding call flow)
                    sig_line = (
                        f"/* Called by {func.name}(): {callee.relpath} line {callee.line_start} */\n"
                        f"/* Reads: {', '.join(callee.reads_vars[:5])} | "
                        f"Writes: {', '.join(callee.writes_vars[:4])} */\n"
                        f"{callee.signature};\n"
                    )
                    parts.append(sig_line)
                    total_size += len(sig_line)

    # ═══ Section 7: Execution flow summary ═══
    if total_size < max_context_chars - 500:
        parts.append("\n/* ══════ EXECUTION FLOW SUMMARY ══════ */")
        parts.append("/*")
        for func in primary_funcs[:6]:
            callers = index.get_callers(func.name)
            caller_str = " | ".join(callers[:3]) if callers else "(?)"
            callees_str = " → ".join(func.calls[:6]) if func.calls else "(none)"
            parts.append(f" * {caller_str} → {func.name}() → {callees_str}")
        parts.append(" */")

    # ═══ Section 8: State machine detection ═══
    if total_size < max_context_chars - 300:
        state_funcs = [f for f in primary_funcs if f.switch_cases and len(f.switch_cases) >= 2]
        if state_funcs:
            parts.append("\n/* ══════ STATE MACHINE DETECTION ══════ */")
            for sf in state_funcs[:3]:
                parts.append(f"/* {sf.name}() has switch states: {', '.join(sf.switch_cases[:12])} */")

    parts.append(f"\n/* [END CODE CONTEXT - {total_size} chars, {len(included_funcs)} functions shown] */")
    return "\n".join(parts)


def _format_function_header(func: FunctionInfo, role: str, index: CodeIndex) -> str:
    """Format function analysis metadata header."""
    header = (
        f"\n/* {'─' * 60} */\n"
        f"/* [{role}] FILE: {func.relpath} (lines {func.line_start}-{func.line_end}) */\n"
        f"/* CALLS: {', '.join(func.calls[:12])} */\n"
        f"/* READS: {', '.join(func.reads_vars[:10])} */\n"
        f"/* WRITES: {', '.join(func.writes_vars[:8])} */\n"
    )
    if func.local_vars:
        local_str = ', '.join(f"{t} {n}" for t, n in func.local_vars[:8])
        header += f"/* LOCALS: {local_str} */\n"
    if func.conditions:
        header += f"/* CONDITIONS ({len(func.conditions)}): */\n"
        for cond in func.conditions[:6]:
            header += f"/*   if ({cond}) */\n"
    if func.switch_cases:
        header += f"/* SWITCH CASES: {', '.join(func.switch_cases[:10])} */\n"
    if func.assignments:
        header += f"/* KEY ASSIGNMENTS: */\n"
        for asgn in func.assignments[:6]:
            header += f"/*   {asgn} */\n"
    # Show callers
    callers = index.get_callers(func.name)
    if callers:
        header += f"/* CALLED BY: {', '.join(callers[:5])} */\n"
    return header


def _format_function_block(func: FunctionInfo, role: str, index: CodeIndex) -> str:
    """Format a complete function block with header + full body."""
    header = _format_function_header(func, role, index)
    return header + f"{func.signature}\n{func.body}\n"


# ─── Keyword Extraction ──────────────────────────────────────────────────────

def _extract_keywords(text: str) -> List[str]:
    """
    Extract meaningful search keywords from requirement/design text.
    
    Priority:
    1. C-style identifiers (snake_case, CamelCase, MACRO_CASE)
    2. Technical domain terms
    3. Regular words (filtered for stopwords)
    """
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "that", "this", "these", "those", "it", "its", "they", "them", "their",
        "and", "but", "or", "not", "no", "if", "when", "then", "than",
        "each", "every", "all", "any", "some", "only", "also", "very",
        "value", "function", "test", "case", "requirement",
        "software", "system", "module",
        "during", "before", "after", "between",
        "given", "expected", "result", "step",
        "upon", "within", "under", "over", "according", "following",
    }

    # Extract C-style identifiers (highest value - these match code directly)
    identifiers = re.findall(r'\b[a-z]+(?:_[a-z0-9]+)+\b', text)   # snake_case
    identifiers += re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', text)      # MACRO_CASE
    identifiers += re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', text)  # CamelCase

    # Regular meaningful words (3+ chars, not stopwords)
    words = re.findall(r'\b[a-zA-Z]\w{2,}\b', text)
    meaningful = [w for w in words if w.lower() not in stopwords]

    # Deduplicate preserving order (identifiers first = higher priority)
    seen = set()
    keywords = []
    for w in identifiers + meaningful:
        key = w.lower()
        if key not in seen and len(w) > 2:
            seen.add(key)
            keywords.append(w)

    # Also split CamelCase and add individual parts
    for w in list(keywords):
        parts = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]{2,}', w)
        for p in parts:
            if len(p) > 2 and p.lower() not in seen and p.lower() not in stopwords:
                seen.add(p.lower())
                keywords.append(p)

    return keywords


def extract_keywords(texts) -> List[str]:
    """Public keyword extractor for the mind-map builder.

    Accepts a single string OR an iterable of strings; returns distinct keywords
    in priority order (identifiers first), de-duplicated case-insensitively across
    all inputs. Thin, stable wrapper over the ported `_extract_keywords`.
    """
    if isinstance(texts, str):
        return _extract_keywords(texts)
    out: List[str] = []
    seen: Set[str] = set()
    for t in texts or []:
        for kw in _extract_keywords(str(t)):
            low = kw.lower()
            if low not in seen:
                seen.add(low)
                out.append(kw)
    return out

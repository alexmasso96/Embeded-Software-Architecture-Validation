"""
Code Map Joiner
===============
Links C AST static indexing data with compiled DWARF symbol data from ELF.
Handles C++ name demangling using cpp_demangle with robust fallbacks.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def demangle_name(name: str) -> str:
    """Demangle an Itanium C++ symbol name. Returns original name on error."""
    try:
        import cpp_demangle
        return cpp_demangle.demangle(name)
    except (ImportError, ValueError, Exception):
        return name

def normalize_cpp_name(name: str) -> str:
    """Normalize a C++ signature/name by removing parameter lists and spaces."""
    name = name.split('(')[0].strip()
    name = name.split()[-1].strip()
    name = name.lstrip('*&')
    return name

def get_base_name(name: str) -> str:
    """Get the last component of a qualified name (after ::)."""
    return name.split('::')[-1].strip()

# Status strings extract_subcalls() returns when disassembly can't proceed — these
# are never real callee names and must not leak into the call graph.
_CAPSTONE_NOISE_PREFIXES = ("Capstone", "Could not", "Disassembly",
                            "No instructions", "Function not found")

def _is_real_call_target(name) -> bool:
    """True for a genuine callee (a named symbol or a raw ``0x…`` address), False
    for the Capstone/lookup status strings that signal a failed disassembly."""
    return bool(name) and not name.startswith(_CAPSTONE_NOISE_PREFIXES)

def _strip_capstone_noise(calls) -> List[str]:
    """Keep only real callees from an extract_subcalls() result, dropping the
    status strings (Capstone errors, 'Function not found', etc.)."""
    return [c for c in calls if _is_real_call_target(c)]

ET_REL = 1   # ELF e_type for a relocatable object (unlinked .o / partial link)

def _elf_is_relocatable(parser) -> bool:
    """True if the parser's ELF is a relocatable object (ET_REL).

    Relocatable objects have *unrelocated* call targets — the linker hasn't filled
    them in yet — so disassembly only ever sees placeholders (typically 0) and can
    never recover a real call graph. We read just the ELF header (magic + e_type,
    the first 18 bytes — one tiny read, EDR-friendly) rather than disassembling.
    Returns False on any read/parse failure so the normal probe still runs."""
    path = getattr(parser, "elf_path", None)
    if not path:
        return False
    try:
        p = str(path)
        if not os.path.isfile(p):
            return False
        with open(p, "rb") as f:
            head = f.read(18)
    except Exception:
        return False
    if len(head) < 18 or head[:4] != b"\x7fELF":
        return False
    # e_type is at offset 16, 2 bytes, in the file's endianness (e_ident[5]: 1=LE).
    endian = "little" if head[5] == 1 else "big"
    return int.from_bytes(head[16:18], endian) == ET_REL

def elf_has_call_tree(parser, *, sample: int = 12) -> bool:
    """Probe whether this ELF yields a usable call tree via disassembly.

    Embedded ELFs are not guaranteed to carry recoverable call edges: stripped
    binaries have no function symbols, relocatable objects (ET_REL) and
    unsupported architectures can't be disassembled, and Capstone may be absent.
    In all those cases the caller should fall back to the *source-derived* call
    graph (#2C). We decide by sampling a few of the largest functions (most likely
    to call something) and checking whether disassembly recovers at least one real
    call edge. Returns False on any failure, so the source fallback is the safe
    default.

    Relocatable (ET_REL) objects are rejected up front via the ELF header: their
    call targets aren't relocated yet, so disassembling them is both slow and
    fruitless — we skip straight to source indexing (#2C)."""
    if parser is None:
        return False
    # Fast path: unlinked relocatable objects can't carry a real call tree — decide
    # from the header alone, before touching Capstone.
    if _elf_is_relocatable(parser):
        return False
    names = []
    db = getattr(parser, "_db", None)
    elf_hash = getattr(parser, "_active_elf_hash", None)
    if db is not None and elf_hash:
        try:
            cur = db.execute(
                "SELECT name FROM elf_functions WHERE elf_hash=? AND size>0 "
                "ORDER BY size DESC LIMIT ?", (elf_hash, sample))
            names = [r["name"] for r in cur.fetchall()]
        except Exception:
            names = []
    else:
        funcs = sorted(getattr(parser, "functions", []),
                       key=lambda f: getattr(f, "size", 0) or 0, reverse=True)
        names = [f.name for f in funcs[:sample]]
    if not names:
        return False
    # extract_subcalls() returns: a real edge list (tree present), a clean empty
    # list (disassembly succeeded, this function is just a leaf), or a list of
    # status strings (disassembly failed). We only declare "no call tree" when
    # disassembly never succeeds across the sample — a leaf-heavy sample must not
    # be mistaken for a broken one, or we'd drop real edges on the no-source path.
    disasm_ok = False
    for name in names:
        try:
            calls = parser.extract_subcalls(name)
        except Exception:
            continue
        if any(_is_real_call_target(c) for c in calls):
            return True
        if not calls:            # clean leaf: Capstone disassembled it fine
            disasm_ok = True
    return disasm_ok

def build_code_map(parser, code_index, *, source_root: str,
                   prefer_source_calls: Optional[bool] = None) -> dict:
    """
    Join the static C AST index data with DWARF extraction records.
    
    Returns a unified CodeMap dictionary:
    {
        "functions": {
            "name": {
                "address": int,
                "size": int,
                "calls": [callee_names],
                "file": str,
                "line_start": int,
                "signature": str,
                "reads_vars": [var_names],
                "writes_vars": [var_names],
                "conditions": [conditions],
                "parameters": [{"name": str, "type": str}],
                "return_type": str
            }
        },
        "global_variables": {
            "name": var_type
        }
    }
    """
    # 1. Retrieve DWARF function and global details from parser
    dwarf_funcs = {}
    dwarf_globals = {}
    dwarf_structures = {}
    
    if parser and getattr(parser, "_db", None) and getattr(parser, "_active_elf_hash", None):
        # Database-backed parser
        db = parser._db
        elf_hash = parser._active_elf_hash
        try:
            cur = db.execute(
                "SELECT name, address, size, parameters, return_type FROM elf_functions WHERE elf_hash=?",
                (elf_hash,)
            )
            for r in cur.fetchall():
                dwarf_funcs[r["name"]] = {
                    "address": r["address"],
                    "size": r["size"],
                    "parameters": json.loads(r["parameters"]) if r["parameters"] else [],
                    "return_type": r["return_type"] or ""
                }
            
            cur_g = db.execute(
                "SELECT name, var_type FROM elf_global_vars WHERE elf_hash=?",
                (elf_hash,)
            )
            for r in cur_g.fetchall():
                dwarf_globals[r["name"]] = r["var_type"]
            
            dwarf_structures = db.get_all_structures(elf_hash)
        except Exception as e:
            logger.error(f"Failed to query DWARF from DB: {e}")
    elif parser:
        # In-memory parser
        for func in getattr(parser, "functions", []):
            dwarf_funcs[func.name] = {
                "address": func.address,
                "size": func.size,
                "parameters": func.parameters,
                "return_type": func.return_type or ""
            }
        dwarf_globals = getattr(parser, "global_vars_dwarf", {})
        dwarf_structures = getattr(parser, "structures", {})

    # #2C: decide whether to disassemble for call edges or fall back to the
    # source-derived call graph. When the ELF carries no usable call tree
    # (stripped / ET_REL / no Capstone), the per-function extract_subcalls() calls
    # only return error strings — so skip them and let the static source edges
    # (ast_func.calls) be the primary graph. The caller may pass the decision
    # explicitly (the Code Map worker does, to avoid re-probing); otherwise we
    # auto-detect once here.
    if prefer_source_calls is None:
        prefer_source_calls = bool(parser) and not elf_has_call_tree(parser)
    use_disasm = bool(parser) and not prefer_source_calls

    # 2. Build mapping tables to resolve mangled/demangled names
    norm_map = {}  # normalized_demangled_name -> original_mangled_name
    base_map = {}  # base_name -> list of original_mangled_names
    
    for mangled_name in dwarf_funcs:
        demangled = demangle_name(mangled_name)
        norm_demangled = normalize_cpp_name(demangled)
        norm_map[norm_demangled] = mangled_name
        
        base = get_base_name(norm_demangled)
        if base not in base_map:
            base_map[base] = []
        base_map[base].append(mangled_name)

    # 3. Join functions
    joined_functions = {}
    
    # Track AST functions to join
    ast_funcs = code_index.functions if code_index else {}
    
    for ast_name, ast_func in ast_funcs.items():
        # Resolve best DWARF match
        dwarf_name = None
        
        # Match 1: exact match
        if ast_name in dwarf_funcs:
            dwarf_name = ast_name
        # Match 2: normalized demangled name match
        elif ast_name in norm_map:
            dwarf_name = norm_map[ast_name]
        # Match 3: base name match (last part of namespace/class)
        else:
            base_ast = get_base_name(ast_name)
            if base_ast in base_map:
                candidates = base_map[base_ast]
                if len(candidates) == 1:
                    dwarf_name = candidates[0]
                else:
                    # Ambiguity: try matching signature/parameters size
                    for cand in candidates:
                        cand_params = dwarf_funcs[cand]["parameters"]
                        if len(cand_params) == len(ast_func.params):
                            dwarf_name = cand
                            break
                    if not dwarf_name:
                        dwarf_name = candidates[0]

        # Extract address/size/subcalls from DWARF if matched
        address = 0
        size = 0
        dwarf_calls = []
        params = [{"name": p[1], "type": p[0]} for p in ast_func.params if p[1]]
        return_type = ast_func.return_type
        
        if dwarf_name:
            df = dwarf_funcs[dwarf_name]
            address = df["address"]
            size = df["size"]
            return_type = df["return_type"] or return_type
            if df["parameters"]:
                params = df["parameters"]
            
            # Extract subcalls using Capstone — unless the ELF has no usable call
            # tree, in which case we rely on the source-derived edges (#2C).
            if use_disasm:
                try:
                    dwarf_calls = _strip_capstone_noise(parser.extract_subcalls(dwarf_name))
                except Exception as e:
                    logger.debug(f"Failed to extract subcalls for {dwarf_name}: {e}")

        # Combine calls from static AST analysis and dynamic Capstone disassembly
        combined_calls = sorted(list(set(ast_func.calls + dwarf_calls)))

        joined_functions[ast_name] = {
            "address": address,
            "size": size,
            "calls": combined_calls,
            "file": ast_func.relpath,
            "line_start": ast_func.line_start,
            "signature": ast_func.signature,
            "reads_vars": ast_func.reads_vars,
            "writes_vars": ast_func.writes_vars,
            "conditions": ast_func.conditions,
            "parameters": params,
            "return_type": return_type
        }

    # Add remaining DWARF functions that weren't in the AST (e.g. assembly/stdlib helpers)
    for mangled_name, df in dwarf_funcs.items():
        demangled = demangle_name(mangled_name)
        norm_demangled = normalize_cpp_name(demangled)
        
        # If this function isn't yet added, add it as a stub
        if norm_demangled not in joined_functions and mangled_name not in joined_functions:
            name_to_use = norm_demangled if "::" in norm_demangled else mangled_name
            
            dwarf_calls = []
            if use_disasm:
                try:
                    dwarf_calls = _strip_capstone_noise(parser.extract_subcalls(mangled_name))
                except Exception:
                    pass

            joined_functions[name_to_use] = {
                "address": df["address"],
                "size": df["size"],
                "calls": dwarf_calls,
                "file": "",
                "line_start": 0,
                "signature": f"{df['return_type']} {name_to_use}()" if df["return_type"] else f"{name_to_use}()",
                "reads_vars": [],
                "writes_vars": [],
                "conditions": [],
                "parameters": df["parameters"],
                "return_type": df["return_type"]
            }

    # 4. Join global variables
    joined_globals = {}
    if code_index:
        for var_name, var_info in code_index.globals.items():
            joined_globals[var_name] = var_info.var_type
            
    # Add any DWARF globals that weren't in the static AST
    for var_name, var_type in dwarf_globals.items():
        if var_name not in joined_globals:
            joined_globals[var_name] = var_type

    # #2D: carry the #define name→value map so hover-tooltips can resolve macros
    # without a re-index. Serialized into code_map_json; absent in older saved maps,
    # so every reader must use dataset.get("defines", {}).
    return {
        "functions": joined_functions,
        "global_variables": joined_globals,
        "structures": dwarf_structures,
        "defines": dict(code_index.defines) if code_index else {}
    }

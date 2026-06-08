"""
Code Map Joiner
===============
Links C AST static indexing data with compiled DWARF symbol data from ELF.
Handles C++ name demangling using cpp_demangle with robust fallbacks.
"""

import json
import logging
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

def build_code_map(parser, code_index, *, source_root: str) -> dict:
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
            
            # Extract subcalls using Capstone if parser is available
            if parser:
                try:
                    dwarf_calls = parser.extract_subcalls(dwarf_name)
                    # Filter out Capstone error messages
                    dwarf_calls = [c for c in dwarf_calls if not c.startswith("Capstone") and not c.startswith("Could not") and not c.startswith("Disassembly") and not c.startswith("No instructions")]
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
            if parser:
                try:
                    dwarf_calls = parser.extract_subcalls(mangled_name)
                    dwarf_calls = [c for c in dwarf_calls if not c.startswith("Capstone") and not c.startswith("Could not") and not c.startswith("Disassembly") and not c.startswith("No instructions")]
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

    return {
        "functions": joined_functions,
        "global_variables": joined_globals,
        "structures": dwarf_structures
    }

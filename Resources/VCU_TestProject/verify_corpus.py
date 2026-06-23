#!/usr/bin/env python3
"""
Verify the generated VCU corpus against the app's REAL code paths:
  1. ELFParser parses every release ELF (functions / params / structs / globals).
  2. Rhapsody import groups ports by component model + expands operations.
  3. SymbolMatcher resolves every architecture Operation to its ELF symbol @100.
  4. The intended inter-release deltas are actually present in the ELF symbols.

Run:  .venv/bin/python ForTesting/VCU_TestProject/verify_corpus.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from core import elf_parser  # noqa: E402
from Application_Logic import Logic_Rhapsody_Import as rh  # noqa: E402
from Application_Logic.Logic_Symbol_Matcher import SymbolMatcher  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RELEASES = ["R1.0", "R2.0", "R3.0", "R4.0", "R5.0"]

PASS, FAIL = "PASS", "FAIL"
fails = 0


def check(cond, msg):
    global fails
    print("  [%s] %s" % (PASS if cond else FAIL, msg))
    if not cond:
        fails += 1


def parse(rel):
    p = elf_parser.ELFParser()
    p.load_elf(os.path.join(HERE, "releases", rel, "vcu_%s.elf" % rel))
    p.extract_all()
    return p


def main():
    print("=== 1. ELF parse contract (backend: depends on rust availability) ===")
    parsers = {}
    func_names = {}
    for rel in RELEASES:
        p = parse(rel)
        parsers[rel] = p
        names = {f.name for f in p.functions}
        func_names[rel] = names
        n_params = sum(1 for f in p.functions if f.parameters)
        print("  %-5s backend=%-16s funcs=%-5d w/params=%-4d structs=%-4d globals=%d"
              % (rel, p.parser_backend, len(p.functions), n_params,
                 len(p.structures), len(p.global_vars_dwarf)))
        check(len(p.functions) > 300, "%s has >300 functions" % rel)
        check(any("_State_t" in s for s in p.structures), "%s exposes *_State_t structs via DWARF" % rel)
        check(n_params > 0, "%s has functions with DWARF parameters" % rel)
        check(len(p.global_vars_dwarf) > 0, "%s exposes DWARF globals" % rel)

    print("\n=== 2. Rhapsody architecture import (CSV) ===")
    csv_path = os.path.join(HERE, "releases", "R5.0", "architecture_ports.csv")
    is_rh, path_col = rh.detect_rhapsody_format(csv_path)
    check(is_rh, "R5.0 ports CSV detected as Rhapsody format (path col=%s)" % path_col)
    cols, rows = rh.read_file(csv_path)
    preview = rh.get_model_preview(rows, path_col)
    print("  models:", ", ".join("%s=%d" % (k, v) for k, v in sorted(preview.items())))
    check(len(preview) == 8, "8 component models detected (got %d)" % len(preview))
    col_map = {"Port Name": "Port", "Required Interface": "Interface",
               "Operations": "Operation", "Direction": "Dir", "Return Type": "Type"}
    data = rh.build_import_data(rows, col_map, path_col, ops_col="Operations")
    total = sum(len(v) for v in data.values())
    check(total > 700, "import expands to >700 operation rows (got %d)" % total)

    print("\n=== 3. Symbol matching (Operations -> ELF symbols @100) ===")
    p = parsers["R5.0"]
    matcher = SymbolMatcher(p)
    ops = [r["Operations"] for r in rows if rh.is_p10_row(r[path_col]) and r["Operations"]]
    ops = sorted(set(ops))
    perfect = 0
    misses = []
    for op in ops:
        name, score = matcher.find_best_match(op, threshold=70)
        if name == op and score == 100:
            perfect += 1
        else:
            misses.append((op, name, score))
    print("  operations=%d  exact@100=%d  misses=%d" % (len(ops), perfect, len(misses)))
    for op, name, score in misses[:10]:
        print("    miss: %-40s -> %s (%s)" % (op, name, score))
    check(len(misses) == 0, "every architecture Operation matches its ELF symbol @100")

    print("\n=== 4. Inter-release deltas visible in ELF symbols ===")
    # Removed: *_LegacyReset present in R1.0, gone in R2.0
    r1_legacy = {n for n in func_names["R1.0"] if n.endswith("_LegacyReset")}
    r2_legacy = {n for n in func_names["R2.0"] if n.endswith("_LegacyReset")}
    check(len(r1_legacy) > 0 and len(r2_legacy) == 0,
          "R1.0 has *_LegacyReset (%d), R2.0 removed them all" % len(r1_legacy))
    # Added: *_SelfTest absent in R2.0, present in R3.0
    r2_st = {n for n in func_names["R2.0"] if n.endswith("_SelfTest")}
    r3_st = {n for n in func_names["R3.0"] if n.endswith("_SelfTest")}
    check(len(r2_st) == 0 and len(r3_st) > 0,
          "R3.0 adds *_SelfTest (%d) not in R2.0" % len(r3_st))
    # New component: ChassisControl (Chs_*) absent R1.0, present R2.0
    check(not any(n.startswith("Chs_") for n in func_names["R1.0"])
          and any(n.startswith("Chs_") for n in func_names["R2.0"]),
          "ChassisControl (Chs_*) introduced in R2.0")
    # New component: ChargingCtrl (Chg_*) absent R2.0, present R3.0
    check(not any(n.startswith("Chg_") for n in func_names["R2.0"])
          and any(n.startswith("Chg_") for n in func_names["R3.0"]),
          "ChargingCtrl (Chg_*) introduced in R3.0")
    # Growth: each release >= previous function count
    counts = [len(func_names[r]) for r in RELEASES]
    check(all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1)),
          "function count is monotonically non-decreasing %s" % counts)
    # Struct field added: State_t gains fault_count by R2.0
    r1_state = parsers["R1.0"].structures
    r2_state = parsers["R2.0"].structures
    sample = next((k for k in r2_state if k.endswith("_State_t")), None)
    if sample and sample in r1_state:
        f1 = {m["name"] for m in r1_state[sample]}
        f2 = {m["name"] for m in r2_state[sample]}
        check("fault_count" in f2 and "fault_count" not in f1,
              "struct %s gained 'fault_count' in R2.0" % sample)

    print("\n%s (%d check(s) failed)" % ("ALL CHECKS PASSED" if fails == 0 else "FAILURES", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

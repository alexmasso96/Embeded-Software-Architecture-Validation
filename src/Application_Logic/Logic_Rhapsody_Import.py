"""
Rhapsody Export Parser
======================
Parses Rhapsody-exported CSV/XLSX port files for architecture import.

Path pattern: Components::P_SW_Components::{Model}::P10_SW_Arch_Public::...
Only rows containing P10_SW_Arch_Public are imported.
Multi-operation cells (comma+newline separated) expand into one row per operation.
"""
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_rhapsody_format(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_rhapsody, path_column_name).
    Heuristic: look for a column whose values contain '::'-delimited paths
    at least 3 segments deep.
    """
    try:
        raw_rows, columns = _read_raw(file_path, max_rows=15)
        if not raw_rows or not columns:
            return False, None
        for idx, col in enumerate(columns):
            for row in raw_rows:
                val = row[idx] if idx < len(row) else ""
                if val and "::" in str(val) and str(val).count("::") >= 3:
                    return True, col
        return False, None
    except Exception:
        return False, None


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def read_file(file_path: str) -> Tuple[List[str], List[dict]]:
    """Returns (columns, rows_as_dicts)."""
    raw_rows, columns = _read_raw(file_path)
    dicts = []
    for row in raw_rows:
        d = {col: (row[i] if i < len(row) else "") for i, col in enumerate(columns)}
        dicts.append(d)
    return columns, dicts


def _read_raw(file_path: str, max_rows: int = None) -> Tuple[List[List[str]], List[str]]:
    """Read CSV or XLSX into (data_rows, header_list)."""
    suffix = Path(file_path).suffix.lower()
    if suffix in ('.xlsx', '.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(rows_iter, [])]
        data = []
        for i, row in enumerate(rows_iter):
            if max_rows is not None and i >= max_rows:
                break
            data.append([str(c) if c is not None else "" for c in row])
        wb.close()
        return data, header
    else:
        with open(file_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, [])
            data = []
            for i, row in enumerate(reader):
                if max_rows is not None and i >= max_rows:
                    break
                data.append(row)
        return data, header


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def extract_model_name(path: str) -> Optional[str]:
    """Returns the 3rd segment of the Rhapsody path (index 2)."""
    parts = path.split("::")
    return parts[2] if len(parts) >= 3 else None


def is_p10_row(path: str) -> bool:
    return "P10_SW_Arch_Public" in path


def detect_required_interface_col(
    columns: List[str], path_col: str, ops_col: Optional[str] = None
) -> Optional[str]:
    """
    Heuristically find the source column holding the required interface name.
    Matches a non-path / non-operations column whose header contains
    'interface' (e.g. 'Required Interface'). Returns None if not found.
    """
    for col in columns:
        if col == path_col or col == ops_col:
            continue
        if "interface" in str(col).lower():
            return col
    return None


# ---------------------------------------------------------------------------
# Operations splitting
# ---------------------------------------------------------------------------

def split_operations(ops_str: str) -> List[str]:
    """
    Splits a Rhapsody Operations cell into individual operation names.
    Cells use comma+newline (or just newline) as separators.
    openpyxl sometimes returns the XML CR entity _x000D_ instead of \r.
    """
    if not ops_str or not str(ops_str).strip():
        return []
    text = str(ops_str).replace('_x000D_', '\r')
    parts = re.split(r'\r?\n', text)
    result = []
    for part in parts:
        # Take only the portion before the first comma (trailing comma is a Rhapsody separator)
        cleaned = part.split(',', 1)[0].strip()
        if cleaned:
            result.append(cleaned)
    return result


# ---------------------------------------------------------------------------
# Model preview
# ---------------------------------------------------------------------------

def get_model_preview(
    rows: List[dict], path_col: str, required_col: Optional[str] = None
) -> Dict[str, int]:
    """
    Returns {model_name: unique_port_count} for P10_SW_Arch_Public rows only.
    Counts unique port names per model (before operation expansion).
    If ``required_col`` is given, rows with a blank value there are excluded so
    the preview matches what build_import_data() will actually import.
    """
    counts: Dict[str, int] = {}
    seen: set = set()
    # port name column is whichever column is not the path col — use the first column
    # We figure it out from the first key that is not path_col.
    for row in rows:
        path = row.get(path_col, "")
        if not is_p10_row(path):
            continue
        if required_col and not str(row.get(required_col, "")).strip():
            continue
        model = extract_model_name(path)
        if not model:
            continue
        # Take first non-path column as port identifier
        port = ""
        for k, v in row.items():
            if k != path_col:
                port = str(v).strip()
                break
        key = (model, port)
        if key not in seen:
            seen.add(key)
            counts[model] = counts.get(model, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Main data builder
# ---------------------------------------------------------------------------

def build_import_data(
    rows: List[dict],
    col_mapping: Dict[str, str],   # {src_col -> table_col_name}; path col absent
    path_col: str,
    ops_col: Optional[str] = None, # source column containing operations (or None)
    required_col: Optional[str] = None,  # source column that must be non-empty
) -> Dict[str, List[dict]]:
    """
    Returns {model_name: [table_row_dict, ...]} for P10_SW_Arch_Public rows.
    Each table_row_dict maps table_col_name -> {"text": value}.
    Rows with multiple operations are expanded: one table row per operation.
    If ``required_col`` is given, P10 rows whose value in that source column is
    blank (e.g. "provided" ports with no required interface) are discarded.
    """
    model_data: Dict[str, List[dict]] = {}
    ops_tbl_col = col_mapping.get(ops_col) if ops_col else None

    for src_row in rows:
        path = src_row.get(path_col, "")
        if not is_p10_row(path):
            continue
        model_name = extract_model_name(path)
        if not model_name:
            continue

        # Discard rows with an empty required-interface value when requested.
        if required_col and not str(src_row.get(required_col, "")).strip():
            continue

        # Build base row dict (all mapped columns except operations)
        base: Dict[str, str] = {}
        for src_col, tbl_col in col_mapping.items():
            if src_col == ops_col:
                continue
            raw = src_row.get(src_col, "")
            base[tbl_col] = str(raw) if raw is not None else ""

        # Skip rows where every mapped non-operations column is empty
        # (e.g. "provided" interface stubs with no port data)
        if all(not v.strip() for v in base.values()):
            ops_str_check = src_row.get(ops_col, "") if ops_col else ""
            if not str(ops_str_check).strip():
                continue

        # Expand operations
        if ops_col and ops_tbl_col:
            ops_str = src_row.get(ops_col, "")
            operations = split_operations(ops_str)
            if not operations:
                operations = [""]
        else:
            operations = None

        if operations and ops_tbl_col:
            for op in operations:
                row_dict = {tbl_col: {"text": val} for tbl_col, val in base.items()}
                row_dict[ops_tbl_col] = {"text": op}
                model_data.setdefault(model_name, []).append(row_dict)
        else:
            row_dict = {tbl_col: {"text": val} for tbl_col, val in base.items()}
            model_data.setdefault(model_name, []).append(row_dict)

    return model_data

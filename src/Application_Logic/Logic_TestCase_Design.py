"""
Test Case Design — condition tokenizer / suggestion engine (pure logic).

Phase 0 (pywebview migration): Qt-free. The Qt tab controller and the
token-completion widgets live in UI/test_case_design.py; after Phase 1 the
FastAPI `testdesign` router uses these for template preview/validation.
"""
import re


def tokenize_partial_condition(text):
    tokens = []
    pos = 0
    n = len(text)
    while pos < n:
        # Skip whitespace
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n:
            break
        
        # Check for column token
        if text[pos] == '[':
            start = pos
            pos += 1
            while pos < n and text[pos] != ']' and text[pos] != '\n':
                pos += 1
            if pos < n and text[pos] == ']':
                pos += 1
                tokens.append(('COLUMN', text[start:pos]))
            else:
                tokens.append(('INCOMPLETE_COLUMN', text[start:pos]))
            continue
            
        # Check for quoted value
        if text[pos] in ("'", '"'):
            quote_char = text[pos]
            start = pos
            pos += 1
            while pos < n and text[pos] != quote_char and text[pos] != '\n':
                pos += 1
            if pos < n and text[pos] == quote_char:
                pos += 1
                tokens.append(('VALUE', text[start:pos]))
            else:
                tokens.append(('INCOMPLETE_VALUE', text[start:pos]))
            continue

        # Check for brace
        if text[pos] == '{':
            tokens.append(('BRACE', '{'))
            pos += 1
            continue

        # Check operators or logicals
        remaining = text[pos:].lower()
        found = False
        for op in ["does not contain", "is not equal", "is equal", "contains", "multiple"]:
            if remaining.startswith(op):
                op_len = len(op)
                if op_len == len(remaining) or not remaining[op_len].isalnum():
                    tokens.append(('OPERATOR', text[pos:pos+op_len]))
                    pos += op_len
                    found = True
                    break
        if found:
            continue

        # Numeric comparison operators following the 'multiple' predicate
        for cmp in [">=", "<=", "==", ">", "<"]:
            if remaining.startswith(cmp):
                tokens.append(('CMP', text[pos:pos+len(cmp)]))
                pos += len(cmp)
                found = True
                break
        if found:
            continue

        for log in ["and", "or"]:
            if remaining.startswith(log):
                log_len = len(log)
                if log_len == len(remaining) or not remaining[log_len].isalnum():
                    tokens.append(('LOGICAL', text[pos:pos+log_len]))
                    pos += log_len
                    found = True
                    break
        if found:
            continue
            
        # Otherwise, word (unquoted value)
        start = pos
        while pos < n and not text[pos].isspace() and text[pos] not in ('[', ']', '{', '}', "'", '"'):
            pos += 1
        if pos == start:
            pos += 1
        word = text[start:pos]
        tokens.append(('WORD', word))
        
    return tokens

def tokenize_condition(condition_text):
    tokens = []
    pos = 0
    n = len(condition_text)
    while pos < n:
        while pos < n and condition_text[pos].isspace():
            pos += 1
        if pos >= n:
            break
            
        if condition_text[pos] == '[':
            start = pos
            pos += 1
            while pos < n and condition_text[pos] != ']':
                pos += 1
            if pos < n:
                pos += 1
            tokens.append(('COLUMN', condition_text[start:pos]))
            continue
            
        if condition_text[pos] in ("'", '"'):
            quote_char = condition_text[pos]
            start = pos
            pos += 1
            while pos < n and condition_text[pos] != quote_char:
                pos += 1
            if pos < n:
                pos += 1
            tokens.append(('VALUE', condition_text[start:pos]))
            continue
            
        remaining = condition_text[pos:].lower()
        found = False
        for op in ["does not contain", "is not equal", "is equal", "contains", "multiple"]:
            if remaining.startswith(op):
                op_len = len(op)
                if op_len == len(remaining) or not remaining[op_len].isalnum() and not remaining[op_len] in ('[', '\'', '"'):
                    tokens.append(('OPERATOR', condition_text[pos:pos+op_len]))
                    pos += op_len
                    found = True
                    break
        if found:
            continue

        for log in ["and", "or"]:
            if remaining.startswith(log):
                log_len = len(log)
                if log_len == len(remaining) or not remaining[log_len].isalnum():
                    tokens.append(('LOGICAL', condition_text[pos:pos+log_len]))
                    pos += log_len
                    found = True
                    break
        if found:
            continue

        # Numeric comparison operators (used by the 'multiple' count predicate)
        for cmp in [">=", "<=", "==", ">", "<"]:
            if remaining.startswith(cmp):
                tokens.append(('CMP', condition_text[pos:pos+len(cmp)]))
                pos += len(cmp)
                found = True
                break
        if found:
            continue

        start = pos
        while pos < n and not condition_text[pos].isspace() and condition_text[pos] not in ('[', ']', "'", '"'):
            pos += 1
        if pos == start:
            pos += 1
        word = condition_text[start:pos]
        tokens.append(('VALUE', word))
        
    return tokens

def get_condition_suggestions_and_prefix(line_text, active_columns, get_unique_values_fn):
    stripped = line_text.strip()
    if stripped == '#':
        return ['#if'], '#'
    if stripped.endswith('#'):
        return ['#if'], '#'

    hash_if_idx = line_text.rfind('#if')
    if hash_if_idx == -1:
        return [], ""

    condition_part = line_text[hash_if_idx + 3:]
    
    tokens = tokenize_partial_condition(condition_part)
    ends_with_space = len(condition_part) > 0 and condition_part[-1].isspace()
    
    if not tokens:
        cols = [f"[{c}]" for c in active_columns]
        return cols, ""

    last_type, last_val = tokens[-1]
    
    if last_type == 'WORD':
        prev_type = tokens[-2][0] if len(tokens) > 1 else None
        if prev_type == 'COLUMN':
            ops = ["contains", "does not contain", "is equal", "is not equal", "multiple"]
            return ops, last_val
        elif prev_type == 'OPERATOR':
            col_name = None
            for t_type, t_val in reversed(tokens[:-1]):
                if t_type == 'COLUMN':
                    col_name = t_val.strip('[]')
                    break
            unique_vals = get_unique_values_fn(col_name) if col_name else []
            common = ["'init'", "'cyclic'", "'0'", "'1'", "'Released'", "'In Work'", "'Retired'", "'Deleted'", "'Reviewed'", "'Not Reviewed'"]
            all_vals = unique_vals + common
            seen = set()
            dedup_vals = []
            for v in all_vals:
                if v not in seen:
                    seen.add(v)
                    dedup_vals.append(v)
            return dedup_vals, last_val
        elif prev_type == 'VALUE':
            suggs = ["AND", "OR", "{"]
            return suggs, last_val
        elif prev_type == 'LOGICAL':
            cols = [f"[{c}]" for c in active_columns]
            return cols, last_val
        else:
            return ["AND", "OR", "{"], last_val

    if ends_with_space:
        if last_type == 'COLUMN':
            ops = ["contains", "does not contain", "is equal", "is not equal", "multiple"]
            return ops, ""
        elif last_type == 'OPERATOR':
            if last_val.strip().lower() == 'multiple':
                return [">", "<", ">=", "<=", "==", "{"], ""
            col_name = None
            for t_type, t_val in reversed(tokens):
                if t_type == 'COLUMN':
                    col_name = t_val.strip('[]')
                    break
            unique_vals = get_unique_values_fn(col_name) if col_name else []
            common = ["'init'", "'cyclic'", "'0'", "'1'", "'Released'", "'In Work'", "'Retired'", "'Deleted'", "'Reviewed'", "'Not Reviewed'"]
            all_vals = unique_vals + common
            seen = set()
            dedup_vals = []
            for v in all_vals:
                if v not in seen:
                    seen.add(v)
                    dedup_vals.append(v)
            return dedup_vals, ""
        elif last_type == 'VALUE':
            return ["AND", "OR", "{"], ""
        elif last_type == 'LOGICAL':
            cols = [f"[{c}]" for c in active_columns]
            return cols, ""
        else:
            return [], ""

    if last_type == 'INCOMPLETE_COLUMN':
        cols_bracket = [f"[{c}]" for c in active_columns]
        return cols_bracket, last_val

    if last_type == 'INCOMPLETE_VALUE':
        col_name = None
        for t_type, t_val in reversed(tokens[:-1]):
            if t_type == 'COLUMN':
                col_name = t_val.strip('[]')
                break
        unique_vals = get_unique_values_fn(col_name) if col_name else []
        common = ["'init'", "'cyclic'", "'0'", "'1'", "'Released'", "'In Work'", "'Retired'", "'Deleted'", "'Reviewed'", "'Not Reviewed'"]
        all_vals = unique_vals + common
        seen = set()
        dedup_vals = []
        for v in all_vals:
            if v not in seen:
                seen.add(v)
                dedup_vals.append(v)
        return dedup_vals, last_val

    if last_type == 'COLUMN':
        return ["contains", "does not contain", "is equal", "is not equal", "multiple"], ""
    if last_type == 'CMP':
        return ["{"], ""
    if last_type == 'OPERATOR':
        if last_val.strip().lower() == 'multiple':
            return [">", "<", ">=", "<=", "==", "{"], ""
        col_name = None
        for t_type, t_val in reversed(tokens[:-1]):
            if t_type == 'COLUMN':
                col_name = t_val.strip('[]')
                break
        unique_vals = get_unique_values_fn(col_name) if col_name else []
        common = ["'init'", "'cyclic'", "'0'", "'1'", "'Released'", "'In Work'", "'Retired'", "'Deleted'", "'Reviewed'", "'Not Reviewed'"]
        all_vals = unique_vals + common
        seen = set()
        dedup_vals = []
        for v in all_vals:
            if v not in seen:
                seen.add(v)
                dedup_vals.append(v)
        return dedup_vals, ""
    if last_type == 'VALUE':
        return ["AND", "OR", "{"], ""
    if last_type == 'LOGICAL':
        cols = [f"[{c}]" for c in active_columns]
        return cols, ""

    return [], ""


# ===========================================================================
# Template evaluation & grouping — ported Qt-free from UI/test_case_design.py.
#
# These are stand-alone pure helpers (no Qt, no controller, no main_window):
# they operate on a ``row_bind_data`` dict ({column_name: value}) and template
# strings. The FastAPI ``testdesign`` router uses them for live preview and the
# HLT Markdown export; the legacy Qt tab keeps its own (identical) copies until
# it is removed. Keeping the logic here means the API and the old UI evaluate
# templates exactly the same way.
# ===========================================================================

# Column families whose values are bookkeeping, not test-case content. Matched
# by name (case-insensitive substring) so they work without column-class info.
_IGNORED_COLUMN_TYPES = {
    "PortStateColumn", "InitColumn", "CyclicColumn", "ReviewColumn",
    "Review Status", "LastResultColumn", "ReleaseResultColumn", "Last Result",
}


def strip_percentage_suffix(text):
    """Remove a trailing fuzzy-match annotation like " (95%)" or
    " (95% similarity)" — match cells carry it; templates want the bare value."""
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r'\s*\(\d+(?:\.\d+)?%\)$', '', text)
    cleaned = re.sub(r'\s*\(\d+(?:\.\d+)?%\s+similarity\)$', '', cleaned)
    return cleaned


def normalize_value(val):
    """Lower-cased, unquoted, percentage-stripped form used for comparisons."""
    if not isinstance(val, str):
        val = str(val)
    val = val.strip()
    if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
        val = val[1:-1]
    val = val.lower().strip()
    val = strip_percentage_suffix(val)
    return val


def evaluate_single_condition(col, op, val, row_bind_data):
    """Evaluate one ``[col] <op> val`` predicate against the bound row."""
    col_name = col.strip('[]')
    actual_val = row_bind_data.get(col_name, "")
    if actual_val is None:
        actual_val = ""

    actual_norm = normalize_value(actual_val)
    expected_norm = normalize_value(val)

    op_lower = op.lower()
    if op_lower == "contains":
        return expected_norm in actual_norm
    elif op_lower == "does not contain":
        return expected_norm not in actual_norm
    elif op_lower == "is equal":
        return actual_norm == expected_norm
    elif op_lower == "is not equal":
        return actual_norm != expected_norm

    return False


def _get_ops_count(row_bind_data):
    """Operation count for the current (grouped) row; 1 when not grouped."""
    try:
        return int(row_bind_data.get("__ops_count__", 1) or 1)
    except (TypeError, ValueError):
        return 1


def _is_int(s):
    try:
        int(str(s).strip())
        return True
    except (TypeError, ValueError):
        return False


def _compare_count(count, cmp, threshold):
    if cmp == '>':
        return count > threshold
    if cmp == '<':
        return count < threshold
    if cmp == '>=':
        return count >= threshold
    if cmp == '<=':
        return count <= threshold
    if cmp in ('==', '='):
        return count == threshold
    return False


def evaluate_condition(condition_text, row_bind_data):
    """Tokenize and evaluate a full ``#if`` condition expression to a bool.

    Supports ``[col] <op> 'val'`` predicates joined by AND/OR, plus the count
    predicate ``[port] multiple`` (>1) / ``[port] multiple >/< N``.
    """
    tokens = tokenize_condition(condition_text)
    if not tokens:
        return False

    eval_list = []
    i = 0
    n = len(tokens)
    while i < n:
        # Count predicate: "[col] multiple" (>1) or "[col] multiple >/< N". The
        # column reference is symbolic; what matters is how many operations this
        # (grouped) test case represents.
        if (i + 1 < n and tokens[i][0] == 'COLUMN'
                and tokens[i+1][0] == 'OPERATOR' and tokens[i+1][1].lower() == 'multiple'):
            count = _get_ops_count(row_bind_data)
            if (i + 3 < n and tokens[i+2][0] == 'CMP'
                    and tokens[i+3][0] in ('VALUE', 'WORD') and _is_int(tokens[i+3][1])):
                res = _compare_count(count, tokens[i+2][1], int(str(tokens[i+3][1]).strip()))
                i += 4
            else:
                res = count > 1
                i += 2
            eval_list.append(res)
        elif i + 2 < n and tokens[i][0] == 'COLUMN' and tokens[i+1][0] == 'OPERATOR' and tokens[i+2][0] in ('VALUE', 'WORD'):
            col = tokens[i][1]
            op = tokens[i+1][1]
            val = tokens[i+2][1]
            res = evaluate_single_condition(col, op, val, row_bind_data)
            eval_list.append(res)
            i += 3
        elif tokens[i][0] == 'LOGICAL':
            eval_list.append(tokens[i][1].upper())
            i += 1
        else:
            i += 1

    return evaluate_boolean_list(eval_list)


def evaluate_boolean_list(eval_list):
    """Reduce a flat [bool, 'AND'|'OR', bool, ...] list (AND binds before OR)."""
    if not eval_list:
        return False

    i = 0
    temp_list = []
    while i < len(eval_list):
        item = eval_list[i]
        if item == 'AND':
            if temp_list and i + 1 < len(eval_list):
                left = temp_list.pop()
                right = eval_list[i+1]
                left_bool = bool(left) if isinstance(left, bool) else False
                right_bool = bool(right) if isinstance(right, bool) else False
                temp_list.append(left_bool and right_bool)
                i += 2
            else:
                i += 1
        else:
            temp_list.append(item)
            i += 1

    if not temp_list:
        return False

    res = bool(temp_list[0]) if isinstance(temp_list[0], bool) else False
    i = 1
    while i < len(temp_list):
        item = temp_list[i]
        if item == 'OR':
            if i + 1 < len(temp_list):
                right = temp_list[i+1]
                right_bool = bool(right) if isinstance(right, bool) else False
                res = res or right_bool
                i += 2
            else:
                i += 1
        else:
            i += 1

    return res


def process_conditional_blocks(template_text, row_bind_data):
    """Resolve ``#if <cond> { ... }`` blocks in a template against the bound row.

    True blocks are inlined (and recursively processed); false blocks (and the
    leading indentation + trailing newline of their line) are removed. Brace
    nesting is matched so nested ``#if`` blocks survive.
    """
    if not isinstance(template_text, str):
        return template_text

    pattern = re.compile(r'#if\s+([^{]+)\{')

    pos = 0
    while True:
        match = pattern.search(template_text, pos)
        if not match:
            break

        start_idx = match.start()
        cond_expr = match.group(1).strip()
        brace_start = match.end() - 1

        brace_count = 0
        matching_close_idx = -1
        for i in range(brace_start, len(template_text)):
            if template_text[i] == '{':
                brace_count += 1
            elif template_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    matching_close_idx = i
                    break

        if matching_close_idx == -1:
            pos = brace_start + 1
            continue

        body = template_text[brace_start + 1: matching_close_idx]

        is_true = evaluate_condition(cond_expr, row_bind_data)

        line_start_idx = start_idx
        while line_start_idx > 0 and template_text[line_start_idx - 1] in (' ', '\t'):
            line_start_idx -= 1

        end_idx = matching_close_idx + 1
        if end_idx < len(template_text) and template_text[end_idx] == '\n':
            end_idx += 1

        if is_true:
            processed_body = process_conditional_blocks(body, row_bind_data)
            if processed_body.startswith('\n'):
                processed_body = processed_body[1:]
            template_text = template_text[:line_start_idx] + processed_body + template_text[end_idx:]
            pos = line_start_idx
        else:
            template_text = template_text[:line_start_idx] + template_text[end_idx:]
            pos = line_start_idx

    return template_text


def bind_data(template, data_dict):
    """Replace every ``[Column Name]`` token with its bound value.

    Matching is case-insensitive so a user-typed ``[model]`` binds the same as the
    canonical ``[Model]`` token (the autocomplete inserts the canonical casing,
    but hand-typed tokens shouldn't silently fail to substitute)."""
    result = template
    for col_name, val in data_dict.items():
        pattern = re.compile(r'\[' + re.escape(col_name) + r'\]', re.IGNORECASE)
        # Use a replacement function so backslashes/groups in the value are literal.
        result = pattern.sub(lambda _m, v=str(val): v, result)
    return result


def get_row_bind_data(row_dict):
    """Flatten one stored row ({col: {text/widget_text}}) to {col: value}."""
    data = {}
    for col_name, cell_info in row_dict.items():
        val = ""
        if isinstance(cell_info, dict):
            if "widget_text" in cell_info and cell_info["widget_text"] is not None:
                val = cell_info["widget_text"]
            else:
                val = cell_info.get("text", "")
        else:
            val = str(cell_info)
        val = strip_percentage_suffix(val if isinstance(val, str) else str(val))
        data[col_name] = val
    return data


def render_template(title_template, design_template, row_bind_data, model_name=None):
    """Bind a (title, design) template pair for one effective row.

    Returns ``(bound_title, bound_design)``. ``[Model]`` is made available when
    ``model_name`` is given. Mirrors the Qt tab's preview/export binding order:
    first resolve ``#if`` blocks, then substitute ``[Column]`` tokens.
    """
    data_dict = dict(row_bind_data)
    if model_name:
        data_dict["Model"] = model_name
    bound_title = process_conditional_blocks(title_template, data_dict)
    bound_design = process_conditional_blocks(design_template, data_dict)
    bound_title = bind_data(bound_title, data_dict)
    bound_design = bind_data(bound_design, data_dict)
    return bound_title, bound_design


def sanitize_filename(name):
    name = re.sub(r'[^\w\s-]', '_', name)
    name = re.sub(r'[-\s_]+', '_', name)
    return name.strip('_ ')


def is_ignored_column(col_name, col_types=None):
    """True for bookkeeping columns excluded from the "row is empty" test.

    ``col_types`` (optional) maps column name → logic type so a column can be
    matched by class as well as by name (e.g. a renamed Port-State column).
    """
    # Internal bookkeeping keys (e.g. __ops_count__) are never table columns.
    if col_name.startswith("__"):
        return True
    name_lower = col_name.lower()
    if "port state" in name_lower or "port status" in name_lower:
        return True
    if "review status" in name_lower or "review" in name_lower:
        return True
    if "(init)" in name_lower:
        return True
    if "(cyclic)" in name_lower:
        return True
    if "result" in name_lower:
        return True
    if col_types:
        if col_types.get(col_name) in _IGNORED_COLUMN_TYPES:
            return True
    return False


def get_port_state_column_name(row_keys, col_types=None):
    """Name of the Port-State column among ``row_keys`` (by name, then type)."""
    for key in row_keys:
        key_lower = key.lower()
        if "port state" in key_lower or "port status" in key_lower:
            return key
    if col_types:
        for name, ctype in col_types.items():
            if ctype == "PortStateColumn":
                return name
    return "Port State"


# ---------------------------------------------------------------------------
# Column resolution (which column is the port / the operations list). The Qt
# tab resolved these from live column objects + DB meta; here we resolve from
# the stored layout (list of (name, type, visible, width)) + DB meta strings.
# ---------------------------------------------------------------------------
def resolve_ops_column(layout, meta_ops=None):
    """Operations column name: DB meta first, then any name containing
    'operation'. '' when there is none."""
    if meta_ops:
        return meta_ops
    for entry in layout:
        if "operation" in entry[0].lower():
            return entry[0]
    return ""


def _port_col_eligible(name, ops_col):
    """A column may serve as the grouping port unless it is the operations
    column, a derived helper, or a state/review/result column."""
    if ops_col and name == ops_col:
        return False
    nl = name.lower()
    if "(match)" in nl or "(init)" in nl or "(cyclic)" in nl:
        return False
    if "state" in nl or "status" in nl or "review" in nl or "result" in nl:
        return False
    return True


def resolve_port_column(layout, meta_port=None, ops_col=""):
    """Column rows are grouped by in Grouped mode. Resolution order: a
    'Port Search' column, then DB meta, then any 'port'-named column — each
    skipping the operations/derived/state columns. '' when there is none."""
    for entry in layout:
        name, ctype = entry[0], entry[1]
        if ctype == "Port Search" and _port_col_eligible(name, ops_col):
            return name
    if meta_port and _port_col_eligible(meta_port, ops_col):
        return meta_port
    for entry in layout:
        name = entry[0]
        if "port" in name.lower() and _port_col_eligible(name, ops_col):
            return name
    return ""


def _build_grouped_rows(rows, port_col, ops_col):
    """Group raw rows by port name into merged ``row_bind_data`` dicts.

    For groups with >1 row the operations column is rendered as a Markdown
    bullet list, and ``__ops_count__`` records the number of operations (which
    powers the ``[port] multiple`` template predicate). Rows with no port name
    each become their own entry. ``rows`` are raw stored rows ({col: cell})."""
    groups = {}    # port_name -> [row_bind_data, ...]
    order = []     # insertion order of port names (preserves table order)

    for row_dict in rows:
        bd = get_row_bind_data(row_dict)
        port_name = bd.get(port_col, "").strip() if port_col else ""
        if port_name:
            if port_name not in groups:
                groups[port_name] = []
                order.append(port_name)
            groups[port_name].append(bd)
        else:
            key = f"__ungrouped_{id(bd)}"
            groups[key] = [bd]
            order.append(key)

    merged_rows = []
    for port_name in order:
        group = groups[port_name]
        if len(group) == 1:
            single = dict(group[0])
            single["__ops_count__"] = 1
            merged_rows.append(single)
        else:
            merged = dict(group[0])
            merged["__ops_count__"] = len(group)
            if ops_col:
                ops_values = [r.get(ops_col, "").strip() for r in group if r.get(ops_col, "").strip()]
                if ops_values:
                    merged[ops_col] = "\n\n" + "\n".join(f"- {op}" for op in ops_values)
            merged_rows.append(merged)

    return merged_rows


def build_effective_rows(raw_rows, grouping, port_col, ops_col):
    """Apply the operation-grouping mode to raw stored rows. Grouped → one entry
    per port (bulleted ops); Independent → one entry per row."""
    if grouping == "grouped":
        return _build_grouped_rows(raw_rows, port_col, ops_col)
    return [get_row_bind_data(r) for r in raw_rows]


def is_effective_row_empty(row_bind_data, col_types=None):
    """True when a (grouped/independent) entry has no content in any non-ignored
    column — the placeholder last row, for instance."""
    for col_name, val in row_bind_data.items():
        if is_ignored_column(col_name, col_types):
            continue
        if str(val).strip():
            return False
    return True


def is_row_renderable(row_bind_data, col_types=None):
    """A row produces a test case only when it is non-empty and not a
    Retired/Deleted port. Returns (renderable, reason) — reason is one of
    'empty', 'retired'/'deleted' (the port-state value), or '' when renderable."""
    if is_effective_row_empty(row_bind_data, col_types):
        return False, "empty"
    psc = get_port_state_column_name(row_bind_data.keys(), col_types)
    psv = row_bind_data.get(psc, "").strip().lower()
    if psv in ("retired", "deleted"):
        return False, psv
    return True, ""


def resolve_tc_id_column(row_keys):
    """The Test-Case-ID column among ``row_keys`` (TC.-named first, then any
    id/tc column, then the first column)."""
    keys = list(row_keys)
    for col in keys:
        col_lower = col.lower()
        if "tc." in col_lower or "tc id" in col_lower or "test case" in col_lower:
            return col
    for col in keys:
        col_lower = col.lower()
        if "id" in col_lower or "tc" in col_lower:
            return col
    return keys[0] if keys else None


def build_model_markdown(model_name, effective_rows, title_template,
                         design_template, col_types=None):
    """Build one model's HLT design Markdown (the export payload), or None when
    the model has no renderable rows. Mirrors the Qt tab's generate_test_cases.
    """
    parts = [
        f"# Test Case Design - {model_name}\n",
        f"This document contains the generated test cases for the "
        f"**{model_name}** architecture model.\n",
    ]

    generated = 0
    for row_bind_data in effective_rows:
        renderable, _reason = is_row_renderable(row_bind_data, col_types)
        if not renderable:
            continue

        row_bind_data = dict(row_bind_data)
        tc_id_col = resolve_tc_id_column(row_bind_data.keys())
        test_case_id = row_bind_data.get(tc_id_col, "") if tc_id_col else ""
        test_case_id = test_case_id.strip() if test_case_id and test_case_id.strip() else "NO_ID"
        if tc_id_col:
            row_bind_data[tc_id_col] = test_case_id
        if "TC. ID" not in row_bind_data:
            row_bind_data["TC. ID"] = test_case_id

        bound_title, bound_design = render_template(
            title_template, design_template, row_bind_data, model_name)

        tc_section = [
            "---",
            f"## Test Case: {bound_title}\n",
            bound_design,
            "\n### Low Level Test Case Design",
            "*(Paste the low-level test cases generated by GitHub Copilot here)*\n",
        ]
        parts.append("\n".join(tc_section))
        generated += 1

    if generated == 0:
        return None
    return "\n".join(parts)


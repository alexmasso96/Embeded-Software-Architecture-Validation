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


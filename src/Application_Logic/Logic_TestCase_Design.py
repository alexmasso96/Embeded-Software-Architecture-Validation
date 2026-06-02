import os
import re
from PyQt6 import QtCore, QtGui, QtWidgets

class TokenCompleter(QtWidgets.QCompleter):
    """
    Custom QCompleter that dynamically fetches and filters the active architecture table columns list.
    """
    def __init__(self, parent=None, get_columns_fn=None):
        super().__init__(parent)
        self.get_columns_fn = get_columns_fn
        self.setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.string_model = QtCore.QStringListModel()
        self.setModel(self.string_model)

    def update_columns(self):
        if self.get_columns_fn:
            cols = self.get_columns_fn()
            self.string_model.setStringList(cols)

class TokenLineEdit(QtWidgets.QLineEdit):
    """
    Custom QLineEdit that triggers dynamic column autocomplete when pressing '['.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.completer = None

    def setCompleter(self, completer):
        self.completer = completer
        completer.setWidget(self)
        completer.activated[str].connect(self.insert_completion)

    def insert_completion(self, completion_text):
        if not self.hasFocus() or (self.completer and self.completer.widget() != self):
            return
        text = self.text()
        pos = self.cursorPosition()
        
        # Look backwards to find the opening '[' trigger
        trigger_pos = -1
        for i in range(pos - 1, -1, -1):
            if text[i] == '[':
                trigger_pos = i
                break
            if text[i] in (']', '\n'):
                break
                
        if trigger_pos != -1:
            new_text = text[:trigger_pos] + '[' + completion_text + ']' + text[pos:]
            self.setText(new_text)
            self.setCursorPosition(trigger_pos + len(completion_text) + 2)

    def keyPressEvent(self, event):
        # Delegate navigation keys to the completer popup if visible
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Return, 
                               QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Tab, 
                               QtCore.Qt.Key.Key_Backtab):
                event.ignore()
                return

        super().keyPressEvent(event)

        if not self.completer:
            return

        text = self.text()
        pos = self.cursorPosition()

        # Check for open token prefix
        found_trigger = False
        prefix = ""
        for i in range(pos - 1, -1, -1):
            if text[i] == '[':
                found_trigger = True
                break
            if text[i] in (']', '\n'):
                break
            prefix = text[i] + prefix

        if not found_trigger:
            self.completer.popup().hide()
            return

        self.completer.update_columns()
        self.completer.setCompletionPrefix(prefix)
        cr = self.cursorRect()
        popup = self.completer.popup()
        width = popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
        cr.setWidth(max(width, 150))
        self.completer.complete(cr)

class TokenTextEdit(QtWidgets.QPlainTextEdit):
    """
    Custom QPlainTextEdit that triggers dynamic column autocomplete when pressing '['.
    Supports smart inline conditional autocomplete suggestions when typing '#' or on #if lines.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.completer = None
        self.controller = None

    def setCompleter(self, completer):
        self.completer = completer
        completer.setWidget(self)
        completer.activated[str].connect(self.insert_completion)

    def insert_completion(self, completion_text):
        if not self.hasFocus() or (self.completer and self.completer.widget() != self):
            return
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        
        # Find start of current line
        line_start = text.rfind('\n', 0, pos) + 1
        line_text = text[line_start:pos]
        
        # 1. Check if completion is a bracketed column token
        if completion_text.startswith('[') and completion_text.endswith(']'):
            trigger_pos = -1
            for i in range(pos - 1, line_start - 1, -1):
                if text[i] == '[':
                    trigger_pos = i
                    break
                if text[i] == ']':
                    break
            if trigger_pos != -1:
                cursor.setPosition(trigger_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(completion_text)
                self.setTextCursor(cursor)
                return

        # 2. Check if completion is `#if` snippet
        if completion_text.startswith('#if'):
            trigger_pos = -1
            for i in range(pos - 1, line_start - 1, -1):
                if text[i] == '#':
                    trigger_pos = i
                    break
            if trigger_pos != -1:
                cursor.setPosition(trigger_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                snippet = "#if [Column] contains 'value' {\n    \n}"
                cursor.insertText(snippet)
                new_cursor = self.textCursor()
                new_cursor.setPosition(trigger_pos + 4)
                self.setTextCursor(new_cursor)
                return

        # 3. For other completions (operator, logical, value, brace)
        # Match typed suffix to avoid duplication
        matched_len = 0
        lower_line = line_text.lower()
        lower_comp = completion_text.lower()
        
        for l in range(len(completion_text), 0, -1):
            prefix_candidate = completion_text[:l]
            if line_text.endswith(prefix_candidate) or lower_line.endswith(prefix_candidate.lower()):
                matched_len = l
                break
                
        if matched_len == 0 and (completion_text.startswith("'") or completion_text.startswith('"')):
            unquoted_comp = completion_text.strip("'\"")
            for l in range(len(unquoted_comp), 0, -1):
                prefix_candidate = unquoted_comp[:l]
                if line_text.endswith(prefix_candidate) or lower_line.endswith(prefix_candidate.lower()):
                    matched_len = l
                    break

        if matched_len > 0:
            cursor.setPosition(pos - matched_len, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(completion_text)
            self.setTextCursor(cursor)
        else:
            cursor.insertText(completion_text)
            self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        # Delegate navigation keys to the completer popup if visible
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Return, 
                               QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Tab, 
                               QtCore.Qt.Key.Key_Backtab):
                event.ignore()
                return

        super().keyPressEvent(event)

        if not self.completer:
            return

        # Ignore modifier keys and navigation keys to prevent unnecessary completion triggers
        if event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right,
                           QtCore.Qt.Key.Key_PageUp, QtCore.Qt.Key.Key_PageDown, QtCore.Qt.Key.Key_Home, QtCore.Qt.Key.Key_End,
                           QtCore.Qt.Key.Key_Shift, QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Meta):
            return

        text = self.toPlainText()
        cursor = self.textCursor()
        pos = cursor.position()

        line_start = text.rfind('\n', 0, pos) + 1
        line_text = text[line_start:pos]

        # Check if we are on a conditional syntax line (contains #if or ends with #)
        is_condition_line = '#if' in line_text or line_text.strip().endswith('#')

        if not is_condition_line:
            # Check for standard [ autocomplete
            found_trigger = False
            prefix = ""
            for i in range(pos - 1, -1, -1):
                if text[i] == '[':
                    found_trigger = True
                    break
                if text[i] in (']', '\n'):
                    break
                prefix = text[i] + prefix

            if not found_trigger:
                self.completer.popup().hide()
                return

            self.completer.update_columns()
            self.completer.setCompletionPrefix(prefix)
            cr = self.cursorRect()
            popup = self.completer.popup()
            width = popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
            cr.setWidth(max(width, 150))
            self.completer.complete(cr)
            return

        # Dynamic autocomplete after #if
        if hasattr(self, 'controller') and self.controller:
            suggs, prefix = self.controller.get_condition_suggestions_and_prefix(line_text)
            if not suggs:
                self.completer.popup().hide()
                return

            self.completer.string_model.setStringList(suggs)
            self.completer.setCompletionPrefix(prefix)
            cr = self.cursorRect()
            popup = self.completer.popup()
            width = popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
            cr.setWidth(max(width, 180))
            self.completer.complete(cr)

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

class HelpDialog(QtWidgets.QDialog):
    """
    Dialog window displaying help and documentation for inline condition syntax and auto-numbering.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Test Case Design - Help & Documentation")
        self.resize(620, 520)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        self.browser = QtWidgets.QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #242424;
                color: #ffffff;
                font-size: 13px;
                padding: 15px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        
        help_html = """
        <h2>Test Case Design — Template Editor</h2>
        <p>Templates are written in <b>standard Markdown</b> with two additional features: column tokens and inline conditionals.</p>

        <h3>1. Standard Markdown</h3>
        <p>The editor and generated files fully support standard Markdown syntax:</p>
        <pre style="background-color: #333; padding: 10px; border-radius: 4px; color: #ddd;">
# Heading 1 &nbsp;&nbsp; ## Heading 2 &nbsp;&nbsp; ### Heading 3
**bold** &nbsp;&nbsp; *italic* &nbsp;&nbsp; `inline code`
---  (horizontal rule)
- bullet item
- [ ] unchecked task &nbsp;&nbsp; - [x] checked task
1. numbered item
> blockquote / precondition
        </pre>

        <h3>2. Column Tokens</h3>
        <p>Reference any architecture table column by wrapping its name in square brackets.
        The special token <b>[Model]</b> resolves to the current architecture model name.</p>
        <pre style="background-color: #333; padding: 10px; border-radius: 4px; color: #5384e4;">
## Verify `[Input Port]` in *[Model]*
- [ ] Set breakpoint in `[Mapped Func]`
        </pre>
        <p>Type <b>[</b> in the editor to open the autocomplete list of available columns.</p>

        <h3>3. Conditional Blocks (#if)</h3>
        <p>Include or exclude content per row using inline conditions:</p>
        <pre style="background-color: #333; padding: 10px; border-radius: 4px; color: #5384e4;">
#if [Column] operator 'value' {
    Content shown only when condition is true
}
        </pre>
        <p><b>Supported operators:</b> <code>contains</code> · <code>does not contain</code> · <code>is equal</code> · <code>is not equal</code> (all case-insensitive)</p>

        <h3>3a. Operation-count predicate (multiple)</h3>
        <p>When operation grouping is <b>Grouped</b>, several operations of the same port collapse into one test case. The <code>multiple</code> predicate lets the template react to how many operations a test case represents, so a port with 40+ operations can be laid out differently from one with two.</p>
        <pre style="background-color: #333; padding: 10px; border-radius: 4px; color: #5384e4;">
#if [port] multiple {            &nbsp;# true when the port has more than one operation
    See the attached operation list.
}
#if [port] multiple &gt; 10 {        &nbsp;# more than 10 operations
    Operations are documented separately.
}
#if [port] multiple &lt; 11 {        &nbsp;# 10 or fewer — inline them
    Operations:
    [Operations]
}
        </pre>
        <p>Comparators: <code>&gt;</code> · <code>&lt;</code> · <code>&gt;=</code> · <code>&lt;=</code> · <code>==</code> followed by a number. The column in <code>[port]</code> is symbolic — the predicate always counts the current test case's operations. In <b>Independent</b> grouping every test case is a single operation, so <code>multiple</code> is always false.</p>

        <p><b>Multiple conditions:</b> combine with <code>AND</code> / <code>OR</code> (AND has higher precedence than OR):</p>
        <pre style="background-color: #333; padding: 10px; border-radius: 4px; color: #5384e4;">
#if [Model] is equal 'LsmDevice' AND [Operations] contains 'Init' {
    ### Init sequence
    - [ ] Verify initialisation is reached exactly once
}
        </pre>
        <p><b>Nesting:</b> <code>#if</code> blocks can be nested to any depth. Multiple sibling blocks at the same level are each evaluated independently.</p>

        <h3>4. Autocomplete</h3>
        <ul>
            <li>Type <b>[</b> to list available column tokens (including <b>[Model]</b>).</li>
            <li>Type <b>#</b> to suggest <b>#if</b>.</li>
            <li>After a column token, type a space for operator suggestions; after an operator, type a space for value suggestions.</li>
        </ul>
        """
        self.browser.setHtml(help_html)
        layout.addWidget(self.browser)
        
        btn_close = QtWidgets.QPushButton("Close", self)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5384e4;
                border: 1px solid #5384e4;
            }
        """)
        btn_close.clicked.connect(self.accept)
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

class TestCaseDesignController(QtCore.QObject):
    __test__ = False
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui
        self.tab_widget = self.ui.tab_2
        self.preview_row_index = -1
        
        # 1. Rename tab_2
        tab_index = self.ui.tabWidget.indexOf(self.tab_widget)
        if tab_index != -1:
            self.ui.tabWidget.setTabText(tab_index, "Test Case Design")
            
        # 2. Build Splitter UI Layout
        self.setup_ui()
        
        # 3. Setup Autocomplete Completers
        self.setup_completers()
        
        # 4. Connect Signals for live preview
        self.txt_project_title.textChanged.connect(self.update_preview)
        self.txt_test_case_design.textChanged.connect(self.update_preview)
        self.btn_prev_preview.clicked.connect(self.show_prev_preview)
        self.btn_next_preview.clicked.connect(self.show_next_preview)

        # 5. Default operation grouping mode
        self._operation_grouping = "grouped"

    def setup_ui(self):
        # Setup vertical layout on the container widget (tab_2)
        self.tab_layout = QtWidgets.QVBoxLayout(self.tab_widget)
        self.tab_layout.setContentsMargins(15, 15, 15, 15)
        
        # QSplitter dividing Input & Preview
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self.tab_widget)
        self.splitter.setHandleWidth(8)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3d3d3d;
                border-radius: 4px;
            }
            QSplitter::handle:hover {
                background-color: #5384e4;
            }
        """)
        
        # Left column (Inputs)
        self.left_widget = QtWidgets.QWidget(self.splitter)
        self.left_layout = QtWidgets.QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(0, 0, 10, 0)
        self.left_layout.setSpacing(10)
        
        # Title Input
        self.lbl_title = QtWidgets.QLabel("Project Title Template:", self.left_widget)
        font = QtGui.QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.lbl_title.setFont(font)
        
        self.txt_project_title = TokenLineEdit(self.left_widget)
        self.txt_project_title.setPlaceholderText("Enter Project Title (e.g., [TC. ID]: Validation of [Input Port])")
        self.txt_project_title.setStyleSheet("""
            QLineEdit {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #5384e4;
            }
        """)
        
        # Design Template Input
        self.lbl_design_layout = QtWidgets.QHBoxLayout()
        self.lbl_design = QtWidgets.QLabel("Test Case Design Template:", self.left_widget)
        self.lbl_design.setFont(font)
        
        self.btn_help = QtWidgets.QPushButton("Help", self.left_widget)
        self.btn_help.setFixedWidth(60)
        self.btn_help.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5384e4;
                border: 1px solid #5384e4;
            }
        """)
        self.btn_help.clicked.connect(self.show_help_dialog)
        
        self.lbl_design_layout.addWidget(self.lbl_design)
        self.lbl_design_layout.addStretch()
        self.lbl_design_layout.addWidget(self.btn_help)
        
        self.txt_test_case_design = TokenTextEdit(self.left_widget)
        self.txt_test_case_design.controller = self
        self.txt_test_case_design.setPlaceholderText(
            "Standard markdown is supported: # ## ### headings, **bold**, *italic*, "
            "--- horizontal rule, - lists, `inline code`, > blockquotes, - [ ] checkboxes.\n\n"
            "Column tokens: type [ to insert a column reference, e.g. [Input Port].\n"
            "Model token: [Model] resolves to the current architecture model name.\n"
            "Conditionals: #if [Column] contains 'value' { ... }\n\n"
            "Example:\n"
            "## Description\n"
            "Verify **[Input Port]** in model *[Model]*.\n\n"
            "## Steps\n"
            "- [ ] Set breakpoint in `[Mapped Func]`\n"
            "- [ ] Run and wait for halt\n"
        )
        self.txt_test_case_design.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                font-family: 'Courier New', Courier, monospace;
            }
            QPlainTextEdit:focus {
                border: 1px solid #5384e4;
            }
        """)
        
        # Grouping mode selector
        grouping_layout = QtWidgets.QHBoxLayout()
        lbl_grouping = QtWidgets.QLabel("Operation grouping:", self.left_widget)
        lbl_grouping.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.cmb_grouping = QtWidgets.QComboBox(self.left_widget)
        self.cmb_grouping.addItem("Grouped — one test case per port  (default)", "grouped")
        self.cmb_grouping.addItem("Independent — one test case per operation", "independent")
        self.cmb_grouping.setStyleSheet("""
            QComboBox {
                background-color: #2e2e2e;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
        """)
        self.cmb_grouping.currentIndexChanged.connect(self._on_grouping_changed)
        grouping_layout.addWidget(lbl_grouping)
        grouping_layout.addWidget(self.cmb_grouping)
        grouping_layout.addStretch()

        self.left_layout.addWidget(self.lbl_title)
        self.left_layout.addWidget(self.txt_project_title)
        self.left_layout.addLayout(self.lbl_design_layout)
        self.left_layout.addLayout(grouping_layout)
        self.left_layout.addWidget(self.txt_test_case_design)
        
        # Right column (Live Preview)
        self.right_widget = QtWidgets.QWidget(self.splitter)
        self.right_layout = QtWidgets.QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(10, 0, 0, 0)
        self.right_layout.setSpacing(10)
        
        self.preview_header_layout = QtWidgets.QHBoxLayout()
        self.lbl_preview = QtWidgets.QLabel("Live Preview:", self.right_widget)
        self.lbl_preview.setFont(font)
        
        self.btn_prev_preview = QtWidgets.QPushButton("◀ Previous", self.right_widget)
        self.btn_prev_preview.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5384e4;
                border: 1px solid #5384e4;
            }
            QPushButton:disabled {
                background-color: #242424;
                color: #666666;
                border: 1px solid #3d3d3d;
            }
        """)
        
        self.lbl_preview_status = QtWidgets.QLabel("", self.right_widget)
        self.lbl_preview_status.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                font-size: 11px;
                font-weight: bold;
                padding: 0 5px;
            }
        """)
        
        self.btn_next_preview = QtWidgets.QPushButton("Next ▶", self.right_widget)
        self.btn_next_preview.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5384e4;
                border: 1px solid #5384e4;
            }
            QPushButton:disabled {
                background-color: #242424;
                color: #666666;
                border: 1px solid #3d3d3d;
            }
        """)
        
        self.preview_header_layout.addWidget(self.lbl_preview)
        self.preview_header_layout.addStretch()
        self.preview_header_layout.addWidget(self.btn_prev_preview)
        self.preview_header_layout.addWidget(self.lbl_preview_status)
        self.preview_header_layout.addWidget(self.btn_next_preview)
        
        self.browser_preview = QtWidgets.QTextBrowser(self.right_widget)
        self.browser_preview.setReadOnly(True)
        self.browser_preview.setStyleSheet("""
            QTextBrowser {
                background-color: #242424;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 15px;
                font-size: 13px;
            }
        """)
        
        self.right_layout.addLayout(self.preview_header_layout)
        self.right_layout.addWidget(self.browser_preview)
        
        self.splitter.addWidget(self.left_widget)
        self.splitter.addWidget(self.right_widget)
        self.splitter.setSizes([800, 800])
        
        self.tab_layout.addWidget(self.splitter)

    def setup_completers(self):
        def get_columns():
            cols = ["Model"]
            if hasattr(self.main_window, 'arch_controller'):
                controller = self.main_window.arch_controller
                if hasattr(controller, 'active_columns'):
                    cols += [col.name for col in controller.active_columns]
            return cols

        self.completer_title = TokenCompleter(self.txt_project_title, get_columns)
        self.txt_project_title.setCompleter(self.completer_title)

        self.completer_design = TokenCompleter(self.txt_test_case_design, get_columns)
        self.txt_test_case_design.setCompleter(self.completer_design)

    def show_help_dialog(self):
        dialog = HelpDialog(self.main_window)
        dialog.exec()

    def get_condition_suggestions_and_prefix(self, line_text):
        active_columns = []
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'active_columns'):
                active_columns = [col.name for col in controller.active_columns]
        return get_condition_suggestions_and_prefix(
            line_text,
            active_columns,
            self.get_unique_values_for_column
        )

    def get_unique_values_for_column(self, column_name):
        if not column_name:
            return []
        unique_vals = []
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'table') and hasattr(controller, 'active_columns'):
                col_idx = -1
                for idx, col in enumerate(controller.active_columns):
                    if col.name == column_name:
                        col_idx = idx
                        break
                if col_idx != -1:
                    row_count = controller.table.rowCount()
                    for r in range(row_count):
                        item = controller.table.item(r, col_idx)
                        widget = controller.table.cellWidget(r, col_idx)
                        val = ""
                        if isinstance(widget, QtWidgets.QComboBox):
                            val = widget.currentText()
                        elif item:
                            val = item.text()
                        val = self.strip_percentage_suffix(val).strip()
                        if val:
                            quoted = f"'{val}'"
                            if quoted not in unique_vals:
                                unique_vals.append(quoted)
        return unique_vals

    def process_conditional_blocks(self, template_text, row_bind_data):
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
            
            body = template_text[brace_start + 1 : matching_close_idx]
            
            is_true = self.evaluate_condition(cond_expr, row_bind_data)
            
            line_start_idx = start_idx
            while line_start_idx > 0 and template_text[line_start_idx - 1] in (' ', '\t'):
                line_start_idx -= 1
            
            end_idx = matching_close_idx + 1
            if end_idx < len(template_text) and template_text[end_idx] == '\n':
                end_idx += 1
            
            if is_true:
                processed_body = self.process_conditional_blocks(body, row_bind_data)
                if processed_body.startswith('\n'):
                    processed_body = processed_body[1:]
                template_text = template_text[:line_start_idx] + processed_body + template_text[end_idx:]
                pos = line_start_idx
            else:
                template_text = template_text[:line_start_idx] + template_text[end_idx:]
                pos = line_start_idx
                
        return template_text

    def evaluate_condition(self, condition_text, row_bind_data):
        tokens = tokenize_condition(condition_text)
        if not tokens:
            return False
        
        eval_list = []
        i = 0
        n = len(tokens)
        while i < n:
            # Count predicate: "[col] multiple" (>1) or "[col] multiple >/< N".
            # The column reference is symbolic; what matters is how many operations
            # this (grouped) test case represents.
            if (i + 1 < n and tokens[i][0] == 'COLUMN'
                    and tokens[i+1][0] == 'OPERATOR' and tokens[i+1][1].lower() == 'multiple'):
                count = self._get_ops_count(row_bind_data)
                if (i + 3 < n and tokens[i+2][0] == 'CMP'
                        and tokens[i+3][0] in ('VALUE', 'WORD') and self._is_int(tokens[i+3][1])):
                    res = self._compare_count(count, tokens[i+2][1], int(str(tokens[i+3][1]).strip()))
                    i += 4
                else:
                    res = count > 1
                    i += 2
                eval_list.append(res)
            elif i + 2 < n and tokens[i][0] == 'COLUMN' and tokens[i+1][0] == 'OPERATOR' and tokens[i+2][0] in ('VALUE', 'WORD'):
                col = tokens[i][1]
                op = tokens[i+1][1]
                val = tokens[i+2][1]
                res = self.evaluate_single_condition(col, op, val, row_bind_data)
                eval_list.append(res)
                i += 3
            elif tokens[i][0] == 'LOGICAL':
                eval_list.append(tokens[i][1].upper())
                i += 1
            else:
                i += 1

        return self.evaluate_boolean_list(eval_list)

    def _get_ops_count(self, row_bind_data) -> int:
        """Operation count for the current (grouped) row; 1 when not grouped."""
        try:
            return int(row_bind_data.get("__ops_count__", 1) or 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _is_int(s) -> bool:
        try:
            int(str(s).strip())
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _compare_count(count: int, cmp: str, threshold: int) -> bool:
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

    def evaluate_boolean_list(self, eval_list):
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

    def evaluate_single_condition(self, col, op, val, row_bind_data):
        col_name = col.strip('[]')
        actual_val = row_bind_data.get(col_name, "")
        if actual_val is None:
            actual_val = ""
            
        actual_norm = self.normalize_value(actual_val)
        expected_norm = self.normalize_value(val)
        
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

    def normalize_value(self, val):
        if not isinstance(val, str):
            val = str(val)
        val = val.strip()
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
        val = val.lower().strip()
        val = self.strip_percentage_suffix(val)
        return val


    def show_prev_preview(self):
        if self.preview_row_index > 0:
            self.preview_row_index -= 1
            self.update_preview()

    def show_next_preview(self):
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'table'):
                if self.preview_row_index < controller.table.rowCount() - 1:
                    self.preview_row_index += 1
                    self.update_preview()

    def _collect_table_raw_rows(self, controller):
        """Read every row of the active table into raw {col: cell_info} dicts."""
        raw_rows = []
        for r in range(controller.table.rowCount()):
            row_dict = {}
            for col_idx, col_obj in enumerate(controller.active_columns):
                cell_info = {}
                item = controller.table.item(r, col_idx)
                cell_info["text"] = item.text() if item else ""
                widget = controller.table.cellWidget(r, col_idx)
                if isinstance(widget, QtWidgets.QComboBox):
                    cell_info["widget_text"] = widget.currentText()
                row_dict[col_obj.name] = cell_info
            raw_rows.append(row_dict)
        return raw_rows

    def _build_effective_preview_rows(self, controller):
        """
        Return (effective_rows, unit_label) for the live preview, honouring the
        operation-grouping mode so the preview matches the generated output.
        In Grouped mode ports collapse to one entry with a bulleted operations
        list (label "Port"); in Independent mode each table row is its own entry
        (label "Row").
        """
        raw_rows = self._collect_table_raw_rows(controller)
        if self._operation_grouping == "grouped":
            return self._build_grouped_rows(raw_rows), "Port"
        return [self.get_row_bind_data(r) for r in raw_rows], "Row"

    def _is_bind_row_empty(self, row_bind_data):
        for col_name, val in row_bind_data.items():
            if self.is_ignored_column(col_name):
                continue
            if val.strip():
                return False
        return True

    def _first_valid_effective_idx(self, effective_rows):
        """First entry that is neither empty nor a Retired/Deleted port."""
        for i, row_bind_data in enumerate(effective_rows):
            if self._is_bind_row_empty(row_bind_data):
                continue
            psc = self.get_port_state_column_name(row_bind_data.keys())
            psv = row_bind_data.get(psc, "").strip()
            if psv.lower() in ["retired", "deleted"]:
                continue
            return i
        return -1

    def update_preview(self):
        # Performance Guard: only render when the Test Case Design tab is the active tab
        if self.ui.tabWidget.currentWidget() != self.tab_widget:
            return

        # Check if the active model has changed
        active_model = None
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'model_manager'):
                active_model = controller.model_manager.get_active_model()
        
        if active_model != getattr(self, 'last_previewed_model', None):
            self.last_previewed_model = active_model
            self.preview_row_index = -1

        # Fetch values from the active architecture table, honouring the
        # operation-grouping mode so the preview matches the generated output.
        data_dict = {}
        if hasattr(self.main_window, 'arch_controller') and hasattr(self.main_window.arch_controller, 'table'):
            controller = self.main_window.arch_controller

            effective_rows, unit_label = self._build_effective_preview_rows(controller)
            n = len(effective_rows)
            if n == 0:
                self.preview_row_index = -1
                self.btn_prev_preview.setEnabled(False)
                self.btn_next_preview.setEnabled(False)
                self.lbl_preview_status.setText("No rows")
                self.browser_preview.setHtml("<p style='color: #888; font-style: italic;'>No rows in active architecture model.</p>")
                return

            # Determine the index to preview (over grouped/independent entries)
            if self.preview_row_index < 0:
                first_valid = self._first_valid_effective_idx(effective_rows)
                self.preview_row_index = first_valid if first_valid != -1 else 0

            # Cap the index within bounds
            if self.preview_row_index >= n:
                self.preview_row_index = n - 1
            if self.preview_row_index < 0:
                self.preview_row_index = 0

            # Update navigation UI
            self.btn_prev_preview.setEnabled(self.preview_row_index > 0)
            self.btn_next_preview.setEnabled(self.preview_row_index < n - 1)
            self.lbl_preview_status.setText(f"{unit_label} {self.preview_row_index + 1} of {n}")

            row_bind_data = effective_rows[self.preview_row_index]

            is_row_empty = self._is_bind_row_empty(row_bind_data)

            port_state_col = self.get_port_state_column_name(row_bind_data.keys())
            port_state_val = row_bind_data.get(port_state_col, "").strip()
            is_retired_or_deleted = port_state_val.lower() in ["retired", "deleted"]

            if is_row_empty:
                self.browser_preview.setHtml(f"<p style='color: #888; font-style: italic;'>{unit_label} {self.preview_row_index + 1} is empty. Enter data in the table to see a preview.</p>")
                return
            elif is_retired_or_deleted:
                self.browser_preview.setHtml(f"<p style='color: #ea9f9f; font-style: italic;'>{unit_label} {self.preview_row_index + 1} Port State is '{port_state_val}'. Test cases are not generated for Retired or Deleted ports.</p>")
                return

            # The grouped/independent bind data is the template substitution source.
            data_dict = dict(row_bind_data)
        else:
            self.btn_prev_preview.setEnabled(False)
            self.btn_next_preview.setEnabled(False)
            self.lbl_preview_status.setText("")

        # Inject model name so [Model] is available in templates
        if active_model:
            data_dict["Model"] = active_model.name

        # Bind template strings
        title_template = self.txt_project_title.text()
        design_template = self.txt_test_case_design.toPlainText()

        # Step 2. Process #if blocks
        bound_title = self.process_conditional_blocks(title_template, data_dict)
        bound_design = self.process_conditional_blocks(design_template, data_dict)

        # Step 3. Bind standard tokens
        bound_title = self.bind_data(bound_title, data_dict)
        bound_design = self.bind_data(bound_design, data_dict)

        # Render Markdown to QTextBrowser
        markdown_content = f"# {bound_title}\n\n{bound_design}"
        self.browser_preview.setMarkdown(markdown_content)


    def bind_data(self, template, data_dict):
        result = template
        for col_name, val in data_dict.items():
            token = f"[{col_name}]"
            result = result.replace(token, str(val))
        return result

    def get_project_title(self):
        return self.txt_project_title.text()

    def get_design_template(self):
        return self.txt_test_case_design.toPlainText()

    def load_data(self, data_dict):
        title = data_dict.get("project_title", "")
        template = data_dict.get("design_template", "")
        grouping = data_dict.get("operation_grouping", "grouped")

        self.txt_project_title.blockSignals(True)
        self.txt_test_case_design.blockSignals(True)
        self.cmb_grouping.blockSignals(True)

        self.txt_project_title.setText(title)
        self.txt_test_case_design.setPlainText(template)
        self._operation_grouping = grouping
        idx = self.cmb_grouping.findData(grouping)
        if idx >= 0:
            self.cmb_grouping.setCurrentIndex(idx)

        self.txt_project_title.blockSignals(False)
        self.txt_test_case_design.blockSignals(False)
        self.cmb_grouping.blockSignals(False)

        self.update_preview()

    def on_tab_changed(self, index):
        if self.ui.tabWidget.widget(index) == self.tab_widget:
            self.update_preview()

    def show_generation_menu(self):
        if not self.main_window.current_project_file:
            QtWidgets.QMessageBox.warning(
                self.main_window, 
                "Project Not Saved", 
                "Please save your project (creates a project file) before generating test cases."
            )
            return

        menu = QtWidgets.QMenu(self.main_window)
        action_current = menu.addAction("Generate for current architecture model")
        action_all = menu.addAction("Generate for all architecture models")

        # Anchor to the Generate button to avoid focus/instant dismissal issues on macOS
        button = self.ui.SideBar_Architecture_Generate_Btn
        pos = button.mapToGlobal(QtCore.QPoint(0, button.height()))
        
        # Defensive fallback: if mapped coordinates are invalid/offscreen, use current cursor position
        if pos.x() <= 0 and pos.y() <= 0:
            pos = QtGui.QCursor.pos()

        action = menu.exec(pos)
        if action == action_current:
            self.generate_test_cases(scope="current")
        elif action == action_all:
            self.generate_test_cases(scope="all")

    def generate_test_cases(self, scope="current"):
        project_path = self.main_window.current_project_file
        if not project_path:
            return

        try:
            # Ensure destination directory exists at project root (parent of .arch directory)
            output_dir = os.path.join(os.path.dirname(project_path), "Test Case Design")
            os.makedirs(output_dir, exist_ok=True)

            # Write rules.md
            rules_path = os.path.join(output_dir, "rules.md")
            rules_content = """# GitHub Copilot Rules for Low-Level ECU Test Case Generation

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
            with open(rules_path, 'w', encoding='utf-8') as f:
                f.write(rules_content)

            # Write copilot_prompt.txt
            prompt_path = os.path.join(output_dir, "copilot_prompt.txt")
            prompt_content = """You are a specialized low-level embedded software test engineer. Your task is to generate low-level test case designs based on the provided ECU source code and the high-level test cases in this file.

CRITICAL INSTRUCTIONS:
1. Ignore all general, pre-set, or default environment testing rules. Rely EXCLUSIVELY on the rules defined in the "rules.md" file.
2. For each test case in the provided file, read the "Given / When / Then" structure.
3. Generate detailed, low-level test steps that correspond to that structure.
4. Place the generated low-level test cases directly under the "### Low Level Test Case Design" header for each test case.
5. Strict constraints check:
   - Are the steps designed for a HiL simulator environment?
   - Did you avoid using CANoe signals (unless simulating active loads is strictly necessary for multicore ECU input retention)?
   - Did you avoid manually bypassing control flow/skipping ifs/goto commands (unless completely untestable otherwise)?
   - Are the debugger steps explicit (e.g., set breakpoint, run, wait for halt, check reached, run, check not reached)?

Please process the test cases below and generate the low-level designs in place.
"""
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt_content)

            # Flush current table inputs to active model cache first
            if hasattr(self.main_window, 'arch_controller'):
                self.main_window.arch_controller.flush_current_data_to_model()

            # Find models to process
            models_to_process = []
            if scope == "current":
                active_model = self.main_window.arch_controller.model_manager.get_active_model()
                if active_model:
                    models_to_process.append(active_model)
            else:
                models_to_process = [m for m in self.main_window.arch_controller.model_manager.models if not m.is_deleted]

            generated_files_count = 0

            for model in models_to_process:
                raw_rows = model.data_cache.get("rows", []) if model.data_cache else []
                if not raw_rows:
                    continue

                # Apply operation grouping
                if self._operation_grouping == "grouped":
                    effective_rows = self._build_grouped_rows(raw_rows)
                else:
                    effective_rows = [self.get_row_bind_data(r) for r in raw_rows]

                model_markdown_parts = []
                model_markdown_parts.append(f"# Test Case Design - {model.name}\n")
                model_markdown_parts.append(f"This document contains the generated test cases for the **{model.name}** architecture model.\n")

                generated_rows_count = 0
                for row_bind_data in effective_rows:

                    # 1. Skip if row is empty (i.e. contains no actual input data, such as placeholder last row)
                    is_row_empty = True
                    for col_name, val in row_bind_data.items():
                        if self.is_ignored_column(col_name):
                            continue
                        if val.strip():
                            is_row_empty = False
                            break
                    if is_row_empty:
                        continue

                    # 2. Skip if Port State is "Retired" or "Deleted"
                    port_state_col = self.get_port_state_column_name(row_bind_data.keys())
                    port_state_val = row_bind_data.get(port_state_col, "").strip()
                    if port_state_val.lower() in ["retired", "deleted"]:
                        continue
                    
                    # Identify Test Case ID column
                    tc_id_col = None
                    for col in row_bind_data.keys():
                        col_lower = col.lower()
                        if "tc." in col_lower or "tc id" in col_lower or "test case" in col_lower:
                            tc_id_col = col
                            break
                    if not tc_id_col:
                        for col in row_bind_data.keys():
                            col_lower = col.lower()
                            if "id" in col_lower or "tc" in col_lower:
                                tc_id_col = col
                                break
                    if not tc_id_col and row_bind_data.keys():
                        tc_id_col = list(row_bind_data.keys())[0]

                    test_case_id = row_bind_data.get(tc_id_col, "") if tc_id_col else ""
                    # Fallback to "NO_ID" if empty/missing instead of skipping
                    if not test_case_id or not test_case_id.strip():
                        test_case_id = "NO_ID"
                    else:
                        test_case_id = test_case_id.strip()

                    # Put test_case_id back into row bind data so it's replaced correctly
                    if tc_id_col:
                        row_bind_data[tc_id_col] = test_case_id
                    if "TC. ID" not in row_bind_data:
                        row_bind_data["TC. ID"] = test_case_id
                    row_bind_data["Model"] = model.name

                    # Bind templates
                    title_template = self.txt_project_title.text()
                    design_template = self.txt_test_case_design.toPlainText()

                    bound_title = self.process_conditional_blocks(title_template, row_bind_data)
                    bound_design = self.process_conditional_blocks(design_template, row_bind_data)

                    bound_title = self.bind_data(bound_title, row_bind_data)
                    bound_design = self.bind_data(bound_design, row_bind_data)

                    # Build section for this test case
                    tc_section = []
                    tc_section.append("---")
                    tc_section.append(f"## Test Case: {bound_title}\n")
                    tc_section.append(bound_design)
                    tc_section.append("\n### Low Level Test Case Design")
                    tc_section.append("*(Paste the low-level test cases generated by GitHub Copilot here)*\n")
                    
                    model_markdown_parts.append("\n".join(tc_section))
                    generated_rows_count += 1

                if generated_rows_count > 0:
                    # Save all test cases of this model to a single model-specific markdown file
                    safe_model_name = self.sanitize_filename(model.name)
                    filename = f"{safe_model_name}_Test_Case_Design.md"
                    file_path = os.path.join(output_dir, filename)

                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("\n".join(model_markdown_parts))

                    generated_files_count += 1

            QtWidgets.QMessageBox.information(
                self.main_window,
                "Generation Complete",
                f"Successfully generated/updated {generated_files_count} test case files in:\n{output_dir}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Generation Error",
                f"An error occurred while generating test cases:\n{str(e)}"
            )

    # ------------------------------------------------------------------
    # Operation grouping helpers
    # ------------------------------------------------------------------

    def _on_grouping_changed(self, _index):
        self._operation_grouping = self.cmb_grouping.currentData()
        # Grouped/independent yield different entry counts, so restart navigation.
        self.preview_row_index = -1
        self.update_preview()

    def get_operation_grouping(self) -> str:
        return self._operation_grouping

    def _get_port_col_name(self) -> str:
        """
        Name of the column identifying a port. Prefers an explicit
        PortSearchColumn, then a stored DB meta, then any column whose name
        contains 'port' (excluding the Port State/Status column). The fallback
        is essential for imported projects, where the port column is plain
        Static Text (e.g. "Port Name") — without it grouping silently no-ops.
        """
        if hasattr(self.main_window, 'arch_controller'):
            from Application_Logic.Logic_Column_Types import PortSearchColumn
            for col in self.main_window.arch_controller.active_columns:
                if isinstance(col, PortSearchColumn):
                    return col.name
        db = getattr(self.main_window, 'project_db', None)
        if db and db.is_open:
            val = db.get_meta("port_column_name")
            if val:
                return val
        if hasattr(self.main_window, 'arch_controller'):
            for col in self.main_window.arch_controller.active_columns:
                name_lower = col.name.lower()
                if "port" in name_lower and "state" not in name_lower and "status" not in name_lower:
                    return col.name
        return ""

    def _get_ops_col_name(self) -> str:
        """
        Return the operations column name: first look in DB meta, then fall back
        to any column whose name contains 'operation' (case-insensitive).
        """
        db = getattr(self.main_window, 'project_db', None)
        if db and db.is_open:
            val = db.get_meta("operations_column_name")
            if val:
                return val
        if hasattr(self.main_window, 'arch_controller'):
            for col in self.main_window.arch_controller.active_columns:
                if "operation" in col.name.lower():
                    return col.name
        return ""

    def _build_grouped_rows(self, rows: list) -> list:
        """
        Groups rows by port name. Returns a list of merged row_bind_data dicts.
        For groups with >1 row the operations column is rendered as a bullet list.
        """
        port_col = self._get_port_col_name()
        ops_col = self._get_ops_col_name()

        groups: dict = {}   # port_name -> [row_bind_data, ...]
        order: list = []    # insertion order of port names (preserves table order)

        for row_dict in rows:
            bd = self.get_row_bind_data(row_dict)
            port_name = bd.get(port_col, "").strip() if port_col else ""
            if port_name:
                if port_name not in groups:
                    groups[port_name] = []
                    order.append(port_name)
                groups[port_name].append(bd)
            else:
                # Rows with no port name get a synthetic unique key so they
                # each appear as their own test case.
                key = f"__ungrouped_{id(bd)}"
                groups[key] = [bd]
                order.append(key)

        merged_rows = []
        for port_name in order:
            group = groups[port_name]
            # __ops_count__ (number of apparitions) powers the "[port] multiple"
            # template predicate. It is internal — is_ignored_column() hides it.
            if len(group) == 1:
                single = dict(group[0])
                single["__ops_count__"] = 1
                merged_rows.append(single)
            else:
                merged = dict(group[0])
                merged["__ops_count__"] = len(group)
                if ops_col:
                    ops_values = [r.get(ops_col, "").strip() for r in group if r.get(ops_col, "").strip()]
                    # Proper Markdown list: a leading blank line + one "- item" per
                    # line so it renders as a real bullet list in the preview and the
                    # generated .md (a single newline would collapse onto one line).
                    if ops_values:
                        merged[ops_col] = "\n\n" + "\n".join(f"- {op}" for op in ops_values)
                merged_rows.append(merged)

        return merged_rows

    def get_row_bind_data(self, row_dict):
        data = {}
        for col_name, cell_info in row_dict.items():
            val = ""
            if isinstance(cell_info, dict):
                if "widget_text" in cell_info:
                    val = cell_info["widget_text"]
                else:
                    val = cell_info.get("text", "")
            else:
                val = str(cell_info)
            val = self.strip_percentage_suffix(val)
            data[col_name] = val
        return data

    def strip_percentage_suffix(self, text):
        if not isinstance(text, str):
            return text
        # Remove trailing " (XX%)" or " (XX.X%)" or " (XX% similarity)"
        cleaned = re.sub(r'\s*\(\d+(?:\.\d+)?%\)$', '', text)
        cleaned = re.sub(r'\s*\(\d+(?:\.\d+)?%\s+similarity\)$', '', cleaned)
        return cleaned


    def sanitize_filename(self, name):
        name = re.sub(r'[^\w\s-]', '_', name)
        name = re.sub(r'[-\s_]+', '_', name)
        return name.strip('_ ')

    def is_ignored_column(self, col_name):
        # Internal bookkeeping keys (e.g. __ops_count__) are never table columns.
        if col_name.startswith("__"):
            return True
        name_lower = col_name.lower()
        # 1. Port State / Port Status
        if "port state" in name_lower or "port status" in name_lower:
            return True
        # 2. Review Status
        if "review status" in name_lower or "review" in name_lower:
            return True
        # 3. Init columns: e.g., "Input Port (Init)", "Mapped Func (Init)"
        if "(init)" in name_lower:
            return True
        # 4. Cyclic columns: e.g., "Input Port (Cyclic)", "Mapped Func (Cyclic)"
        if "(cyclic)" in name_lower:
            return True
        # 5. Result columns: e.g., "Last Result", "Release Result"
        if "result" in name_lower:
            return True
            
        # Fallback/dynamic check based on active column classes
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'active_columns'):
                for col_obj in controller.active_columns:
                    if col_obj.name == col_name:
                        cls_name = col_obj.__class__.__name__
                        if cls_name in ["PortStateColumn", "ReviewColumn", "InitColumn", "CyclicColumn", "LastResultColumn", "ReleaseResultColumn"]:
                            return True
        return False

    def get_port_state_column_name(self, row_keys):
        # First, try to find a key matching port state/status patterns
        for key in row_keys:
            key_lower = key.lower()
            if "port state" in key_lower or "port status" in key_lower:
                return key
        # Second, fallback to class name check from active columns
        if hasattr(self.main_window, 'arch_controller'):
            controller = self.main_window.arch_controller
            if hasattr(controller, 'active_columns'):
                for col_obj in controller.active_columns:
                    if col_obj.__class__.__name__ == "PortStateColumn":
                        return col_obj.name
        return "Port State"

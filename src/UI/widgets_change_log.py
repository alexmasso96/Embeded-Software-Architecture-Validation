import html
from PyQt6 import QtWidgets, QtCore, QtGui

class ChangeLogWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tab Widget
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        # --- Sub-tab 1: Manual ---
        self.tab_manual = QtWidgets.QWidget()
        manual_layout = QtWidgets.QVBoxLayout(self.tab_manual)
        manual_layout.setContentsMargins(10, 10, 10, 10)

        # Top row layout
        top_row = QtWidgets.QHBoxLayout()
        self.lbl_compare = QtWidgets.QLabel("Compare Active Release with:")
        self.lbl_compare.setStyleSheet("font-weight: bold;")
        self.cmb_compare_release = QtWidgets.QComboBox()
        self.cmb_compare_release.setMinimumWidth(180)
        
        self.btn_compute_diffs = QtWidgets.QPushButton("Compute Release Diffs")
        self.btn_compute_diffs.setStyleSheet("font-weight: bold; padding: 5px 10px;")
        
        self.lbl_diff_info = QtWidgets.QLabel("")
        self.lbl_diff_info.setStyleSheet("color: #666; font-size: 11px;")

        top_row.addWidget(self.lbl_compare)
        top_row.addWidget(self.cmb_compare_release)
        top_row.addWidget(self.btn_compute_diffs)
        top_row.addWidget(self.lbl_diff_info, 1)
        manual_layout.addLayout(top_row)

        # Main splitter
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        manual_layout.addWidget(self.splitter, 1)

        # Column 1: File Browser
        self.file_list = QtWidgets.QListWidget()
        self.file_list.setStyleSheet(
            "QListWidget { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; font-size: 12px; }"
            "QListWidget::item { padding: 6px; border-bottom: 1px solid #3d3d3d; }"
            "QListWidget::item:selected { background-color: #2a82da; color: white; }"
            "QListWidget::item:hover { background-color: #3d3d3d; }"
        )
        self.splitter.addWidget(self.file_list)

        # Splitter for Column 2 and 3
        self.diff_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.diff_splitter)

        # Column 2: Old Code View
        self.txt_old = QtWidgets.QTextEdit()
        self.txt_old.setReadOnly(True)
        self.txt_old.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.txt_old.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #444444; font-family: monospace; font-size: 10pt; }"
        )
        self.diff_splitter.addWidget(self.txt_old)

        # Column 3: New Code View
        self.txt_new = QtWidgets.QTextEdit()
        self.txt_new.setReadOnly(True)
        self.txt_new.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.txt_new.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #444444; font-family: monospace; font-size: 10pt; }"
        )
        self.diff_splitter.addWidget(self.txt_new)

        # Synchronize scrollbars
        self._scrolling = False
        self.txt_old.verticalScrollBar().valueChanged.connect(self._sync_old_to_new)
        self.txt_new.verticalScrollBar().valueChanged.connect(self._sync_new_to_old)

        # Set default splitter stretch
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 4)
        self.diff_splitter.setStretchFactor(0, 1)
        self.diff_splitter.setStretchFactor(1, 1)

        self.tabs.addTab(self.tab_manual, "Manual Change Log")

        # --- Sub-tab 2: AI ---
        self.tab_ai = QtWidgets.QWidget()
        ai_layout = QtWidgets.QVBoxLayout(self.tab_ai)
        ai_layout.setContentsMargins(10, 10, 10, 10)

        self.txt_ai_changelog = QtWidgets.QTextBrowser()
        self.txt_ai_changelog.setOpenExternalLinks(True)
        self.txt_ai_changelog.setStyleSheet(
            "QTextBrowser { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #444444; font-family: sans-serif; font-size: 11pt; padding: 10px; }"
        )
        ai_layout.addWidget(self.txt_ai_changelog)

        self.tabs.addTab(self.tab_ai, "AI Change Log")

    def _sync_old_to_new(self, value):
        if not self._scrolling:
            self._scrolling = True
            self.txt_new.verticalScrollBar().setValue(value)
            self._scrolling = False

    def _sync_new_to_old(self, value):
        if not self._scrolling:
            self._scrolling = True
            self.txt_old.verticalScrollBar().setValue(value)
            self._scrolling = False

    def set_diff_view(self, aligned_old, aligned_new):
        """Expects lists of tuples (line_content, line_type)"""
        html_old = self._build_html(aligned_old)
        html_new = self._build_html(aligned_new)
        
        self.txt_old.setHtml(html_old)
        self.txt_new.setHtml(html_new)

    def _build_html(self, lines):
        html_parts = []
        html_parts.append("<html><body style='margin: 0; padding: 0; font-family: monospace; font-size: 10pt; line-height: 1.4; background-color: #1e1e1e;'>")
        for content, line_type in lines:
            escaped = html.escape(content)
            if line_type == "deleted":
                style = "background-color: #4c1b1b; color: #ff8888; margin: 0; padding: 1px 4px; white-space: pre;"
            elif line_type == "added":
                style = "background-color: #133820; color: #88ff88; margin: 0; padding: 1px 4px; white-space: pre;"
            elif line_type == "empty":
                style = "background-color: #1e1e1e; color: transparent; margin: 0; padding: 1px 4px; white-space: pre; user-select: none;"
                escaped = " "
            elif line_type == "header":
                style = "background-color: #1b324c; color: #88ccff; font-weight: bold; margin: 0; padding: 1px 4px; white-space: pre;"
            else:
                style = "color: #d4d4d4; margin: 0; padding: 1px 4px; white-space: pre;"
            
            html_parts.append(f"<div style='{style}'>{escaped}</div>")
        html_parts.append("</body></html>")
        return "".join(html_parts)

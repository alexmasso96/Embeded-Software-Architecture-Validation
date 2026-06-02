"""
Rhapsody Export Import Dialog
Two-step dialog:
  Step 1 — map source CSV/XLSX columns to architecture table columns
  Step 2 — map extracted model names to existing architecture models
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QGroupBox,
)
from PyQt6.QtCore import Qt


_SKIP = "<Skip>"
_CREATE_PREFIX = "<Create new: "


class RhapsodyImportDialog(QDialog):
    """
    Parameters
    ----------
    file_path            : path to the source file (for display only)
    columns              : list of source column names
    rows                 : list of row dicts from read_file()
    path_col             : the column auto-detected as the Rhapsody path
    ops_col              : the column auto-detected as containing operations
                           (None if not found)
    model_preview        : {model_name: port_count} from get_model_preview()
    existing_table_cols  : [col_name, ...] of current architecture table columns
    existing_model_names : [model_name, ...] of current architecture models

    Outputs (read after exec() returns True)
    ----------------------------------------
    col_mapping   : {src_col -> table_col_name}  (path col not included)
    model_mapping : {model_name -> target_model_name | "<Create New>"}
    new_columns   : [col_name, ...]  new table columns to create
    """

    def __init__(
        self,
        file_path: str,
        columns: list,
        rows: list,
        path_col: str,
        ops_col,
        model_preview: dict,
        existing_table_cols: list,
        existing_model_names: list,
        parent=None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.columns = columns
        self.rows = rows
        self.path_col = path_col
        self.ops_col = ops_col
        self.model_preview = model_preview
        self.existing_table_cols = existing_table_cols
        self.existing_model_names = existing_model_names

        # Outputs
        self.col_mapping: dict = {}
        self.model_mapping: dict = {}
        self.new_columns: list = []

        self._col_combos: dict = {}
        self._model_combos: dict = {}

        self.setWindowTitle("Rhapsody Export Import")
        self.resize(800, 620)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(QLabel(f"<b>File:</b> {os.path.basename(self.file_path)}"))

        root.addWidget(self._build_col_section())
        root.addWidget(self._build_model_section())
        root.addLayout(self._build_buttons())

    def _build_col_section(self) -> QGroupBox:
        grp = QGroupBox("Step 1 — Map source columns to table columns")
        lay = QVBoxLayout(grp)

        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(["Source Column", "Sample Values", "Table Column"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.horizontalHeader().resizeSection(2, 240)
        tbl.setRowCount(len(self.columns))
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.setMaximumHeight(min(40 + 32 * len(self.columns), 200))

        sample_rows = self.rows[:3]

        for i, src_col in enumerate(self.columns):
            # Source column name
            tbl.setItem(i, 0, _ro_item(src_col))

            # Sample values
            samples = []
            for row in sample_rows:
                v = str(row.get(src_col, "")).replace("\r\n", " / ").replace("\n", " / ").strip()[:50]
                if v:
                    samples.append(v)
            tbl.setItem(i, 1, _ro_item(" | ".join(samples[:3])))

            # Target combo / label
            if src_col == self.path_col:
                lbl = QLabel("  ⚙ Used for model detection")
                lbl.setStyleSheet("color: #5384e4; font-style: italic;")
                tbl.setCellWidget(i, 2, lbl)
            else:
                combo = self._make_col_combo(src_col)
                tbl.setCellWidget(i, 2, combo)
                self._col_combos[src_col] = combo

        lay.addWidget(tbl)
        return grp

    def _make_col_combo(self, src_col: str) -> QComboBox:
        combo = QComboBox()
        # Existing table columns first
        for col_name in self.existing_table_cols:
            combo.addItem(col_name)
        # Create-new suggestion using the source column name
        create_label = f"{_CREATE_PREFIX}{src_col}>"
        combo.addItem(create_label)
        combo.addItem(_SKIP)

        # Auto-select: exact name match → that column; ops col → create new; else create new
        src_norm = src_col.lower().replace(" ", "").replace("_", "")
        matched = False
        for j, col_name in enumerate(self.existing_table_cols):
            if src_norm == col_name.lower().replace(" ", "").replace("_", ""):
                combo.setCurrentIndex(j)
                matched = True
                break
        if not matched:
            idx = combo.findText(create_label)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return combo

    def _build_model_section(self) -> QGroupBox:
        count = len(self.model_preview)
        grp = QGroupBox(f"Step 2 — Map extracted architecture models  ({count} detected from P10_SW_Arch_Public)")
        lay = QVBoxLayout(grp)

        hint = QLabel(
            "Each extracted model can be mapped to an existing architecture model "
            "or a new one will be created automatically."
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(["Extracted Model", "Ports", "Architecture Model"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)

        sorted_models = sorted(self.model_preview.items())
        tbl.setRowCount(len(sorted_models))

        for i, (model_name, port_count) in enumerate(sorted_models):
            tbl.setItem(i, 0, _ro_item(model_name))
            cnt_item = _ro_item(str(port_count))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(i, 1, cnt_item)

            combo = QComboBox()
            combo.addItem("<Create New>")
            for existing in self.existing_model_names:
                combo.addItem(existing)
            if model_name in self.existing_model_names:
                combo.setCurrentText(model_name)
            tbl.setCellWidget(i, 2, combo)
            self._model_combos[model_name] = combo

        lay.addWidget(tbl)
        return grp

    def _build_buttons(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_import = QPushButton("Import")
        btn_import.setDefault(True)
        btn_import.setStyleSheet("font-weight: bold; padding: 6px 20px;")
        btn_import.clicked.connect(self._on_import)

        lay.addWidget(btn_cancel)
        lay.addWidget(btn_import)
        return lay

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def _on_import(self):
        self.col_mapping = {}
        self.new_columns = []

        for src_col, combo in self._col_combos.items():
            choice = combo.currentText()
            if choice == _SKIP:
                continue
            if choice.startswith(_CREATE_PREFIX) and choice.endswith(">"):
                new_name = choice[len(_CREATE_PREFIX):-1]
                self.col_mapping[src_col] = new_name
                if new_name not in self.new_columns:
                    self.new_columns.append(new_name)
            else:
                self.col_mapping[src_col] = choice

        self.model_mapping = {
            model_name: combo.currentText()
            for model_name, combo in self._model_combos.items()
        }
        self.accept()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ro_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item

"""
#8.2 — Port-state propagation picker.

When an architecture model leaves the 'In Work' state (In Work → Released/Retired),
the old behaviour cascaded the change onto *every* In Work port silently. This dialog
makes the cascade explicit: the user picks which columns hold the Port Name / Port
State, sees the unique In Work ports, and ticks exactly which ones should follow the
model to the new state.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QComboBox, QListWidget, QListWidgetItem,
                             QPushButton, QLabel)
from PyQt6.QtCore import Qt

from Application_Logic.Logic_Architecture_Models import _cell_text
from .StyledMessageBox import DIALOG_STYLESHEET


class PortPropagationDialog(QDialog):
    """Confirm/select which ports follow a model state change.

    Constructed from plain data (``columns``, ``rows``, ``new_status``) so it's
    decoupled from the table controller and unit-testable in isolation:
      * ``columns`` — list of ``(name, type_str)`` describing the active table columns.
      * ``rows``    — the model's row dicts (``{col_name: {"text"/"widget_text": ...}}``).
      * ``new_status`` — the model's new state the selected ports should move to.
    """

    def __init__(self, columns, rows, new_status, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propagate Port State")
        self.resize(460, 480)
        self.setStyleSheet(DIALOG_STYLESHEET)
        self._columns = [(str(c[0]), str(c[1]) if len(c) > 1 else "")
                         for c in (columns or []) if c]
        self._rows = rows or []
        self._new_status = new_status
        self.init_ui()
        self._repopulate_ports()

    # -- UI -----------------------------------------------------------------
    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel(
            f"Select the ports whose Port State should follow the model to "
            f"<b>{self._new_status}</b>.<br/>"
            f"Only ports currently <b>In Work</b> are listed."))

        form = QFormLayout()
        self.cmb_port_name = QComboBox()
        self.cmb_port_state = QComboBox()
        for name, _type in self._columns:
            self.cmb_port_name.addItem(name)
            self.cmb_port_state.addItem(name)
        self._select_default(self.cmb_port_name, "PortSearchColumn")
        self._select_default(self.cmb_port_state, "PortStateColumn")
        self.cmb_port_name.currentIndexChanged.connect(self._repopulate_ports)
        self.cmb_port_state.currentIndexChanged.connect(self._repopulate_ports)
        form.addRow("Port Name column:", self.cmb_port_name)
        form.addRow("Port State column:", self.cmb_port_state)
        layout.addLayout(form)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, stretch=1)

        sel_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_none = QPushButton("Select None")
        self.btn_all.clicked.connect(self.on_select_all)
        self.btn_none.clicked.connect(self.on_select_none)
        sel_layout.addWidget(self.btn_all)
        sel_layout.addWidget(self.btn_none)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_confirm = QPushButton("Confirm Propagation")
        self.btn_confirm.setDefault(True)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _select_default(self, combo, type_str):
        """Select the first column of ``type_str``; fall back to index 0."""
        for i, (_name, t) in enumerate(self._columns):
            if t == type_str:
                combo.setCurrentIndex(i)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    # -- scanning -----------------------------------------------------------
    def get_port_name_column(self):
        return self.cmb_port_name.currentText()

    def get_port_state_column(self):
        return self.cmb_port_state.currentText()

    def scan_in_work_ports(self):
        """Ordered, de-duplicated port names whose Port State is currently
        'In Work' (a grouped search over the rows using the selected columns)."""
        name_col = self.get_port_name_column()
        state_col = self.get_port_state_column()
        seen = set()
        ports = []
        for row in self._rows:
            if _cell_text(row.get(state_col)) != "In Work":
                continue
            pname = _cell_text(row.get(name_col))
            if not pname or pname in seen:
                continue
            seen.add(pname)
            ports.append(pname)
        return ports

    def _repopulate_ports(self):
        self.list_widget.clear()
        for pname in self.scan_in_work_ports():
            item = QListWidgetItem(pname)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)

    def has_ports(self):
        return self.list_widget.count() > 0

    def on_select_all(self):
        self._set_all(Qt.CheckState.Checked)

    def on_select_none(self):
        self._set_all(Qt.CheckState.Unchecked)

    def _set_all(self, state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def get_selected_ports(self):
        return [self.list_widget.item(i).text()
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).checkState() == Qt.CheckState.Checked]

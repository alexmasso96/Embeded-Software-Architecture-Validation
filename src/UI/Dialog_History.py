from PyQt6 import QtWidgets, QtCore, QtGui
import datetime

class HistoryDialog(QtWidgets.QDialog):
    def __init__(self, history_entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change History Log (ASPICE-Compliant)")
        self.resize(800, 500)
        
        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        
        # Info Label
        info_label = QtWidgets.QLabel(
            "<b>ASPICE Traceability Change Log</b><br>"
            "This log is read-only and permanently tracks all modifications to the architecture.",
            self
        )
        layout.addWidget(info_label)
        
        # Table
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "User", "Architecture Model", "Change Description"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Headers resize policy
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.table)
        
        # Close Button
        self.btn_close = QtWidgets.QPushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)
        
        # Populate
        self.populate_history(history_entries)
        
    def populate_history(self, entries):
        # Sort entries newest-first
        sorted_entries = sorted(
            entries, 
            key=lambda x: x.get("timestamp", ""), 
            reverse=True
        )
        
        self.table.setRowCount(len(sorted_entries))
        for row, entry in enumerate(sorted_entries):
            ts_str = entry.get("timestamp", "")
            try:
                dt = datetime.datetime.fromisoformat(ts_str)
                # Convert to local/UTC display
                ts_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                ts_display = ts_str
                
            user = entry.get("user", "")
            model = entry.get("model", "N/A")
            desc = entry.get("description", "")
            
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(ts_display))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(user))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(model))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(desc))

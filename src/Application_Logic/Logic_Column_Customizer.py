from PyQt6  import QtWidgets, QtCore, QtGui


class ColumnCustomizer(QtWidgets.QDialog):
    def __init__(self, current_config, logic_options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Table Columns")
        self.available_logics = logic_options # List of keys like [Port Search, Function Search, ...]
        self.init_ui(current_config)

    def init_ui(self, current_config):
        layout = QtWidgets.QVBoxLayout(self)

        # Top Area: Create a New Column
        create_layout = QtWidgets.QHBoxLayout()
        self.new_name_input = QtWidgets.QLineEdit()
        self.new_name_input.setPlaceholderText("Enter Column Name...")
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(self.available_logics)
        add_btn = QtWidgets.QPushButton("Add New")
        add_btn.clicked.connect(self._add_custom_item)

        create_layout.addWidget(self.new_name_input)
        create_layout.addWidget(self.type_combo)
        create_layout.addWidget(add_btn)
        layout.addLayout(create_layout)

        # Middle Area: Drag and Drop lists
        # Note: Items will store data as "Name | Type"
        list_layout = QtWidgets.QHBoxLayout()
        self.active_list = self._create_drag_list()
        for name, l_type in current_config:
            item = QtWidgets.QListWidgetItem(f"{name} | {l_type}")
            self.active_list.addItem(item)

        list_layout.addWidget(QtWidgets.QLabel("Active Columns:"))
        list_layout.addWidget(self.active_list)
        layout.addLayout(list_layout)

        # Bottom Area: OK / Cancel Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_drag_list(self):
        l = QtWidgets.QListWidget()
        l.setDragEnabled(True)
        l.setAcceptDrops(True)
        l.setDropIndicatorShown(True)
        # Move mode allows dragging items between lists
        l.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        l.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        return l

    def _add_custom_item(self):
        name = self.new_name_input.text().strip()
        l_type = self.type_combo.currentText()
        if name:
            self.active_list.addItem(f"{name} | {l_type}")
            self.new_name_input.clear()

    def get_selected_config(self):
        config = []
        for i in range(self.active_list.count()):
            text = self.active_list.item(i).text()
            name, l_type = text.split(" | ")
            config.append((name, l_type))
        return config
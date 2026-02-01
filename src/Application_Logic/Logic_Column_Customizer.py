from PyQt6  import QtWidgets, QtCore, QtGui


class ColumnCustomizer(QtWidgets.QDialog):
    def __init__(self, current_config, logic_options, locked_columns=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Table Columns")
        self.resize(600, 500)  # Issue 4: Bigger window
        self.available_logics = logic_options # List of keys like [Port Search, Function Search, ...]
        self.locked_columns = locked_columns if locked_columns else set()
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
        # Note: Items will store data as "Name | Type" and CheckState for visibility
        list_layout = QtWidgets.QHBoxLayout()
        self.active_list = self._create_drag_list()
        
        # Config is now (name, type, visible)
        for col_data in current_config:
            # Handle legacy config (name, type) or new (name, type, visible)
            name, l_type = col_data[0], col_data[1]
            visible = col_data[2] if len(col_data) > 2 else None
            
            self._add_list_item(name, l_type, visible)

        list_layout.addWidget(QtWidgets.QLabel("Active Columns:"))
        list_layout.addWidget(self.active_list)
        layout.addLayout(list_layout)
        
        # Delete Button
        self._add_side_buttons(list_layout)

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

    def _add_side_buttons(self, layout):
        btn_layout = QtWidgets.QVBoxLayout()
        
        rename_btn = QtWidgets.QPushButton("Rename Selected")
        rename_btn.clicked.connect(self._rename_selected_item)
        btn_layout.addWidget(rename_btn)

        del_btn = QtWidgets.QPushButton("Delete Selected")
        del_btn.clicked.connect(self._delete_selected_item)
        btn_layout.addWidget(del_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _add_list_item(self, name, l_type, visible=None):
        item = QtWidgets.QListWidgetItem(f"{name} | {l_type}")
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        
        # Issue 2: Init and Cyclic columns follow default behavior (Auto) unless overwritten.
        # We use a Tristate checkbox: PartiallyChecked = Auto (None), Checked = Force Show (True), Unchecked = Force Hide (False)
        is_tristate = "InitColumn" in l_type or "CyclicColumn" in l_type
        
        if is_tristate:
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserTristate)
            if visible is None:
                item.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
            elif visible is True:
                item.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        else:
            # Standard columns are binary
            check_state = QtCore.Qt.CheckState.Checked if (visible is None or visible is True) else QtCore.Qt.CheckState.Unchecked
            item.setCheckState(check_state)

        self.active_list.addItem(item)

    def _get_unique_name(self, base_name):
        """Ensures the name is unique by appending (1), (2) etc. if needed."""
        existing_names = set()
        for i in range(self.active_list.count()):
            text = self.active_list.item(i).text()
            if " | " in text:
                existing_names.add(text.split(" | ")[0])
        
        if base_name not in existing_names:
            return base_name
            
        counter = 1
        while True:
            candidate = f"{base_name} ({counter})"
            if candidate not in existing_names:
                return candidate
            counter += 1

    def _add_custom_item(self):
        name = self.new_name_input.text().strip()
        l_type = self.type_combo.currentText()
        if name:
            # Issue 1: Ensure unique name
            name = self._get_unique_name(name)

            self._add_list_item(name, l_type, visible=True)
            
            # Auto-add dependent columns so user can manage them
            if "Search" in l_type:
                self._add_list_item(f"{name} (Match)", "Static Text", visible=True)
                
                if "Port" in l_type or "Function" in l_type:
                    self._add_list_item(f"{name} (Init)", "InitColumn", visible=None) # Default to Auto
                    self._add_list_item(f"{name} (Cyclic)", "CyclicColumn", visible=None) # Default to Auto

            self.new_name_input.clear()

    def _rename_selected_item(self):
        row = self.active_list.currentRow()
        if row < 0: return
        
        item = self.active_list.item(row)
        text = item.text()
        old_name, l_type = text.split(" | ")
        
        # Constraint 2: Review Status cannot be renamed
        if l_type == "Review Status":
             QtWidgets.QMessageBox.warning(self, "Cannot Rename", "The 'Review Status' column cannot be renamed.")
             return

        # Constraint 2: Locked columns cannot be renamed
        if old_name in self.locked_columns:
             QtWidgets.QMessageBox.warning(self, "Cannot Rename", f"The column '{old_name}' cannot be renamed because it is locked or contains reviewed data.")
             return

        # Constraint 3: Dependent columns cannot be renamed directly
        suffixes = [" (Match)", " (Init)", " (Cyclic)"]
        is_dependent = False
        for suffix in suffixes:
            if old_name.endswith(suffix):
                is_dependent = True
                break
        
        if is_dependent:
             QtWidgets.QMessageBox.warning(self, "Cannot Rename", "Dependent columns (Match, Init, Cyclic) cannot be renamed directly.\nPlease rename the parent Search column instead.")
             return

        # Prompt for new name
        new_name, ok = QtWidgets.QInputDialog.getText(self, "Rename Column", "Enter new name:", text=old_name)
        if not ok or not new_name.strip():
            return
            
        new_name = new_name.strip()
        if new_name == old_name:
            return

        # Issue 1: Ensure uniqueness
        new_name = self._get_unique_name(new_name)

        # Perform Rename
        # 1. Rename the item itself
        item.setText(f"{new_name} | {l_type}")
        
        # 2. Rename dependents (Hard coded tags)
        for i in range(self.active_list.count()):
            other_item = self.active_list.item(i)
            other_text = other_item.text()
            other_name, other_type = other_text.split(" | ")
            
            for suffix in suffixes:
                if other_name == f"{old_name}{suffix}":
                    # Found a dependent, rename it to match new parent
                    new_dep_name = f"{new_name}{suffix}"
                    other_item.setText(f"{new_dep_name} | {other_type}")

    def _delete_selected_item(self):
        row = self.active_list.currentRow()
        if row < 0: return
        
        item = self.active_list.item(row)
        name = item.text().split(" | ")[0]
        
        suffixes = [" (Match)", " (Init)", " (Cyclic)"]

        # Constraint 1: Dependent columns cannot be deleted directly
        for suffix in suffixes:
            if name.endswith(suffix):
                QtWidgets.QMessageBox.warning(self, "Cannot Delete", 
                    f"The column '{name}' cannot be deleted directly.\nPlease delete the parent Search column instead.")
                return
        
        # Issue 2: Prevent deletion if column is locked (contains Reviewed data)
        if name in self.locked_columns:
            QtWidgets.QMessageBox.warning(self, "Cannot Delete", 
                f"The column '{name}' cannot be deleted because it is locked or contains reviewed data.")
            return

        # Constraint 3: Prevent deletion if any dependent column is locked
        for suffix in suffixes:
            dep_name = f"{name}{suffix}"
            if dep_name in self.locked_columns:
                 QtWidgets.QMessageBox.warning(self, "Cannot Delete", 
                    f"The column '{name}' cannot be deleted because its dependent column '{dep_name}' is locked.")
                 return

        self.active_list.takeItem(row)
        
        # Auto-delete dependents
        rows_to_delete = []
        for i in range(self.active_list.count()):
            other_item = self.active_list.item(i)
            other_name = other_item.text().split(" | ")[0]
            
            for suffix in suffixes:
                if other_name == f"{name}{suffix}":
                    rows_to_delete.append(i)
                    break
        
        # Delete in reverse order to preserve indices
        for r in sorted(rows_to_delete, reverse=True):
            self.active_list.takeItem(r)

    def get_selected_config(self):
        config = []
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            text = item.text()
            name, l_type = text.split(" | ")
            
            # Determine visibility override
            # Issue 2: Map Tristate back to None/True/False
            state = item.checkState()
            if state == QtCore.Qt.CheckState.PartiallyChecked:
                is_visible = None # Auto
            elif state == QtCore.Qt.CheckState.Checked:
                is_visible = True # Force Show
            else:
                is_visible = False # Force Hide
            
            config.append((name, l_type, is_visible))
        return config
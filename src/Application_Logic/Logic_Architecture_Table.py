from PyQt6 import QtWidgets, QtCore, QtGui
from .Logic_Symbol_Matcher import SymbolMatcher
from .Logic_Column_Customizer import ColumnCustomizer
from .Logic_Column_Types import TableColumn, PortSearchColumn, FunctionSearchColumn, VariableSearchColumn, ReviewColumn, InitColumn, CyclicColumn
from .Logic_User_Interaction import UserInteractionLogic


class ArchitectureTabController:
    """
    Handles all logic related to the Architecture Validation Tab
    """

    def __init__(self, main_window):
        self.main_window = main_window # Store the actual QMainWindow
        self.ui = main_window.ui # Get the UI components from it
        self.table = self.ui.Architecture_Table
        self.sidebar_list = self.ui.SideBar_Architecture_List

        # Registry of Logic Types available to the user
        self.available_logics = {
            "Port Search": PortSearchColumn,
            "Function Search": FunctionSearchColumn,
            "Variable Search": VariableSearchColumn,
            "Review Status": ReviewColumn,
            "Static Text": TableColumn,
            "InitColumn": InitColumn,     # Exposed for Customizer
            "CyclicColumn": CyclicColumn, # Exposed for Customizer
        }

        # Current configuration: (Column Name) -> (Logic Instance)
        self.active_columns = []
        # Config is now: (Name, Logic Key, User_Visible_Override)
        # We explicitly list all columns now so the Customizer can see them.
        self.active_config = [
            ("TC. ID", "Static Text", True),
            ("Input Port", "Port Search", True), ("Input Port (Match)", "Static Text", True), ("Input Port (Init)", "InitColumn", None), ("Input Port (Cyclic)", "CyclicColumn", None),
            ("Mapped Func", "Function Search", True), ("Mapped Func (Match)", "Static Text", True), ("Mapped Func (Init)", "InitColumn", None), ("Mapped Func (Cyclic)", "CyclicColumn", None),
            ("Mapped Parameter", "Variable Search", True), ("Mapped Parameter (Match)", "Static Text", True),
            ("Review Status", "Review Status", True),
        ]
        self.active_columns = []
        # Issue 1: Track columns that have EVER been part of a reviewed row
        self.permanently_locked_columns = set()
        
        self._rebuild_column_objects()
        self._setup_table_style()
        self._connect_signals()

    def _rebuild_column_objects(self):
        """
        Converts the config tuples (active_config) into actual logic instances
        """
        config = getattr(self, 'active_config', [])
        self.active_columns = []

        for col_data in config:
            name, logic_key = col_data[0], col_data[1]
            visible = col_data[2] if len(col_data) > 2 else None
            
            logic_cls = self.available_logics.get(logic_key, TableColumn)
            
            col_obj = logic_cls(name)
            col_obj.user_visible = visible
            self.active_columns.append(col_obj)

    def _setup_table_style(self):
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()

        # 1. Update column count based on active objects
        col_count = len(self.active_columns)
        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels([c.name for c in self.active_columns])

        # 2. Apply dynamic widths and modes
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(50)

        for i, col_obj in enumerate(self.active_columns):
            # Set the width defined in the logic class
            self.table.setColumnWidth(i, col_obj.width)

        # Hide Init column by default until a match is found
        self.refresh_init_column_state()
        self.refresh_cyclic_column_state()

        # 3. Row handling
        if self.table.rowCount() == 0:
            self.table.insertRow(0)
            self._initialize_row_widgets(0)

    def refresh_init_column_state(self):
        """
        Master logic for the Init column. Handles all 11 cases:
        1. Function contains 'init' => Init = 1
        2. Function does not contain 'init' => Init = 0
        3. User overwrites Init cell => User_overwrite = 1
        4. User_overwrite=1, init=0, func changes to init => Init=1, color=purple
        5. User_overwrite=1, init=1, func changes to non-init => Init=0, color=purple
        6. Review Status=Reviewed, func changes to non-init => Init=0, color=purple
        7. Review Status=Reviewed, func changes to init => Init=1, color=purple
        8. Purple=True, user clicks cell => color clears (handled in InitColumn.on_change)
        9. User_overwrite=1, user clears cell => User_overwrite=0, auto-fill
        10. Init column visible as long as any init is declared.
        11. No purple when User_overwrite=1 and column reappears (handled by tracking)
        """
        self.table.blockSignals(True)
        init_mappings = [i for i, obj in enumerate(self.active_columns) if isinstance(obj, InitColumn)]

        for init_idx in init_mappings:
            res_idx = init_idx - 1  # The associated Match/Dropdown column
            any_init_found = False
            
            # Issue 1: Overwrite default behavior if settings changed
            init_col = self.active_columns[init_idx]

            for row in range(self.table.rowCount()):
                widget = self.table.cellWidget(row, res_idx)
                current_func_name = ""
                func_is_init = False

                if isinstance(widget, QtWidgets.QComboBox):
                    current_func_name = widget.currentText()
                    if "init" in current_func_name.lower():
                        func_is_init = True

                item = self.table.item(row, init_idx)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    self.table.setItem(row, init_idx, item)

                # If there's no function name, we shouldn't be setting an init value,
                # unless the user has manually overridden it.
                is_user_override_check = UserInteractionLogic.is_item_user_changed(item)
                if not current_func_name and not is_user_override_check:
                    # If the cell has text, clear it. Otherwise, do nothing.
                    if item.text():
                        item.setText("")
                    continue

                is_user_override = UserInteractionLogic.is_item_user_changed(item)
                last_func = UserInteractionLogic.get_last_function(item)
                review_status = UserInteractionLogic.get_review_status(self.table, row, self)

                # Determine if function has changed since last check
                func_changed = (last_func is not None and last_func != current_func_name)

                # --- Core Logic ---
                new_val = None
                should_be_purple = False

                if is_user_override:
                    # Cases 4, 5, 11: User has overwritten the value
                    if func_changed:
                        # The function changed, we need to update and warn
                        new_val = "1" if func_is_init else "0"
                        should_be_purple = True
                    else:
                        # No function change, keep user's value, no new purple
                        # Check if it was already purple (Case 11 - don't re-apply purple on reappear)
                        should_be_purple = UserInteractionLogic.is_purple(item)
                        # Keep existing value
                        new_val = item.text()

                elif review_status == "Reviewed":
                    # Cases 6, 7: Reviewed status, respect function changes
                    if func_changed:
                        new_val = "1" if func_is_init else "0"
                        should_be_purple = True
                    else:
                        # No change, auto-calculate but don't mark purple
                        new_val = "1" if func_is_init else "0"
                        should_be_purple = UserInteractionLogic.is_purple(item) # Keep existing purple if any
                else:
                    # Cases 1, 2: Default auto-calculation
                    new_val = "1" if func_is_init else "0"
                    should_be_purple = False  # Auto mode is never purple

                # --- Apply State ---
                if new_val is not None:
                    item.setText(new_val)

                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

                if should_be_purple:
                    UserInteractionLogic.mark_purple(item)
                # Note: We don't clear purple here; it's cleared on click (Case 8)

                # Update the stored function name for the next comparison
                UserInteractionLogic.set_last_function(item, current_func_name)

                if item.text() == "1":
                    any_init_found = True

            # Case 10: Show this Init column if any cell is '1'
            # Issue 1: Respect manual visibility override if set, otherwise use auto-hide
            if init_col.user_visible is not None:
                self.table.setColumnHidden(init_idx, not init_col.user_visible)
            else:
                self.table.setColumnHidden(init_idx, not any_init_found)

        self.table.blockSignals(False)

    def refresh_cyclic_column_state(self):
        """
        Master logic for the Cyclic column.
        Parses function names for 'Cyclic' (10) or 'XXms' (XX).
        Follows the same override/purple logic as InitColumn.
        """
        self.table.blockSignals(True)
        cyclic_mappings = [i for i, obj in enumerate(self.active_columns) if isinstance(obj, CyclicColumn)]

        for cyc_idx in cyclic_mappings:
            # Determine res_idx (Match column)
            # If the column immediately preceding is InitColumn, skip it (Match is -2)
            res_idx = cyc_idx - 1
            if cyc_idx > 0 and isinstance(self.active_columns[cyc_idx - 1], InitColumn):
                res_idx = cyc_idx - 2
            
            # Issue 1: Overwrite default behavior if settings changed
            cyc_col = self.active_columns[cyc_idx]

            any_cyclic_found = False

            for row in range(self.table.rowCount()):
                widget = self.table.cellWidget(row, res_idx)
                current_func_name = ""
                
                if isinstance(widget, QtWidgets.QComboBox):
                    current_func_name = widget.currentText()

                item = self.table.item(row, cyc_idx)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    self.table.setItem(row, cyc_idx, item)

                expected_val = CyclicColumn.get_expected_value(current_func_name)
                
                # Check if we should process this row
                is_user_override_check = UserInteractionLogic.is_item_user_changed(item)
                if not current_func_name and not is_user_override_check:
                    if item.text():
                        item.setText("")
                    continue

                is_user_override = UserInteractionLogic.is_item_user_changed(item)
                last_func = UserInteractionLogic.get_last_function(item)
                review_status = UserInteractionLogic.get_review_status(self.table, row, self)

                func_changed = (last_func is not None and last_func != current_func_name)

                new_val = None
                should_be_purple = False

                if is_user_override:
                    if func_changed:
                        new_val = expected_val
                        should_be_purple = True
                    else:
                        should_be_purple = UserInteractionLogic.is_purple(item)
                        new_val = item.text()
                elif review_status == "Reviewed":
                    if func_changed:
                        new_val = expected_val
                        should_be_purple = True
                    else:
                        new_val = expected_val
                        should_be_purple = UserInteractionLogic.is_purple(item)
                else:
                    new_val = expected_val
                    should_be_purple = False

                if new_val is not None:
                    item.setText(new_val)
                
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

                if should_be_purple:
                    UserInteractionLogic.mark_purple(item)

                UserInteractionLogic.set_last_function(item, current_func_name)

                if item.text() != "0" and item.text() != "":
                    any_cyclic_found = True

            # Issue 1: Respect manual visibility override if set, otherwise use auto-hide
            if cyc_col.user_visible is not None:
                self.table.setColumnHidden(cyc_idx, not cyc_col.user_visible)
            else:
                self.table.setColumnHidden(cyc_idx, not any_cyclic_found)

        self.table.blockSignals(False)

    def _initialize_row_widgets(self, row):
        """Ensures widgets like the Review dropdown are created for a new row."""
        for col_idx, col_obj in enumerate(self.active_columns):
            # Fetch existing text if available (e.g. when restoring columns)
            text = ""
            item = self.table.item(row, col_idx)
            if item:
                text = item.text()
            col_obj.on_change(self.table, row, col_idx, text, self)

    def get_column_index_by_type(self, type_name):
        """Finds the index of the first column matching a specific logic type."""
        for i, col_obj in enumerate(self.active_columns):
            # Check if the class name matches or use a type attribute
            if type_name in type(col_obj).__name__:
                return i
        return -1

    def _connect_signals(self):
        # Connect the Generate Button
        self.ui.SideBar_Architecture_Generate_Btn.clicked.connect(self.handle_generate)
        # Listen for changes to trigger fuzzy match and dynamic rows
        self.table.itemChanged.connect(self.on_item_changed)

        self.table.horizontalHeader().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_column_customizer)

    def open_column_customizer(self, pos):
        """Opens the drag-and-drop dialog and updates table columns."""
        # Issue 3: Init and Cyclic columns should not be presented as individual types
        # Filter them out of the options passed to the UI
        logic_options = [
            key for key in self.available_logics.keys() 
            if key not in ["InitColumn", "CyclicColumn", "Review Status"]
        ]
        
        # Issue 1: Identify locked columns (rows that are Reviewed OR were previously reviewed)
        # We accumulate into self.permanently_locked_columns
        review_idx = self.get_column_index_by_type("ReviewColumn")
        if review_idx != -1:
            # Lock the Review Column itself so it cannot be deleted
            self.permanently_locked_columns.add(self.active_columns[review_idx].name)

            for row in range(self.table.rowCount()):
                status = UserInteractionLogic.get_review_status(self.table, row, self)
                if status == "Reviewed":
                    # Lock columns ONLY if they have data in this reviewed row
                    for col_idx, col_obj in enumerate(self.active_columns):
                        has_data = False
                        
                        # Check widget text (e.g. Search Columns)
                        widget = self.table.cellWidget(row, col_idx)
                        if isinstance(widget, QtWidgets.QComboBox):
                            if widget.currentText().strip():
                                has_data = True
                        # Check item text (e.g. Static Text, Init)
                        item = self.table.item(row, col_idx)
                        if item and item.text().strip():
                            has_data = True
                        
                        if has_data:
                            self.permanently_locked_columns.add(col_obj.name)

        dialog = ColumnCustomizer(self.active_config, logic_options, self.permanently_locked_columns, self.main_window)
        if dialog.exec():
            new_config = dialog.get_selected_config()
            self.apply_new_columns(new_config)

    def apply_new_columns(self, column_names):
        """
        Reconfigures the table columns while trying to preserve existing data.
        'new_config' is a list of (name, logic_type) tuples.
        """
        # Store current data before we rebuild
        old_data = []
        old_headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]

        for row in range(self.table.rowCount()):
            row_data = {}
            for col_idx, header in enumerate(old_headers):
                # Fix: Grab data from widget if present (e.g. Search Dropdowns), otherwise item
                val = ""
                widget = self.table.cellWidget(row, col_idx)
                if isinstance(widget, QtWidgets.QComboBox):
                    val = widget.currentText()
                    # Clean up percentage if present to ensure clean search/init logic restoration
                    if " (" in val and val.endswith("%)"):
                        val = val.rsplit(" (", 1)[0]
                else:
                    item = self.table.item(row, col_idx)
                    val = item.text() if item else ""
                row_data[header] = val
            old_data.append(row_data)

        # Update the configuration and objects
        self.active_config = column_names
        self._rebuild_column_objects()
        
        # Issue 3: Clear table contents (including widgets) to prevent duplication bugs
        self.table.clearContents()
        # Note: clearContents does not remove rows, just data/widgets.

        # Reconfigure the UI
        self.table.blockSignals(True)
        self._setup_table_style()

        # Map old data back to new column positions by Header Name
        for row_idx, row_dict in enumerate(old_data):
            for col_idx, col_obj in enumerate(self.active_columns):
                val = row_dict.get(col_obj.name, "")
                if val:
                    self.table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(val))
        
        # Issue 3: Force widget regeneration for all rows/cols
        for row in range(self.table.rowCount()):
            self._initialize_row_widgets(row)

        self.table.blockSignals(False)

    def populate_from_parser(self, parser):
        """
        Initializes the matcher when a new ELF/JSON is successfully loaded
        """
        if not parser:
            print("Error: Received empty parser in ArchitectureTabController")
            return

        self.parser = parser
        self.matcher = SymbolMatcher(parser)

        # UI Feedback
        self.ui.statusbar.showMessage("Matcher ready. Enter Port Names to begin matching.")
        print(f"Matcher initialized with {len(self.matcher.search_pool)} symbols.")

    def on_item_changed(self, item):
        """
        Unified handler for fuzzy matching, dynamic row addition, and cleanup.
        """
        if self.table.signalsBlocked():
            return

        row = item.row()
        
        # Issue 2: Reset review status on any edit (covers Static Text, Init, Cyclic, etc.)
        UserInteractionLogic.reset_review_status(self.table, row, self)
        
        col_idx = item.column()
        text = item.text().strip()

        self.table.blockSignals(True)
        try:
            # Only notify the specific strategy that belongs to the edited column
            if col_idx < len(self.active_columns):
                strategy = self.active_columns[col_idx]
                strategy.on_change(self.table, row, col_idx, text, self)

            # Issue 4: Ensure ReviewColumn (and others) initialize when row gets content.
            # We trigger the ReviewColumn logic specifically if it exists and wasn't the one edited.
            review_idx = self.get_column_index_by_type("ReviewColumn")
            if review_idx != -1 and review_idx != col_idx:
                # Passing empty text forces it to check "has_content" logic
                self.active_columns[review_idx].on_change(self.table, row, review_idx, "", self)

            # Auto-add new row logic
            if row == self.table.rowCount() - 1 and text != "":
                new_row = self.table.rowCount()
                self.table.insertRow(new_row)
                self._initialize_row_widgets(new_row)
        finally:
            self.table.blockSignals(False)

    def handle_generate(self):
        print("Generation triggered...")
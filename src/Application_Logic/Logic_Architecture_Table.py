from PyQt6 import QtWidgets, QtCore, QtGui
import os
from .Logic_Project_Saving import ProjectSaver
from .Logic_Symbol_Matcher import SymbolMatcher
from .Logic_Column_Customizer import ColumnCustomizer
from .Logic_Column_Types import TableColumn, PortSearchColumn, FunctionSearchColumn, VariableSearchColumn, ReviewColumn, InitColumn, CyclicColumn, PortStateColumn, LastResultColumn, ReleaseResultColumn
from .Logic_User_Interaction import UserInteractionLogic
from .Logic_User_Interaction import UserInteractionLogic
from .Logic_Architecture_Models import ArchitectureManager, ArchitectureListModel
from .Logic_Release_Manager import ReleaseManager
from UI.Dialog_Architecture_Edit import ArchitectureEditDialog
from UI.Dialog_Restore_Model import RestoreModelDialog

class ArchitectureTabController:
    """
    Handles all logic related to the Architecture Validation Tab
    """

    def __init__(self, main_window):
        self.main_window = main_window # Store the actual QMainWindow
        self.ui = main_window.ui # Get the UI components from it
        self.table = self.ui.Architecture_Table
        self.sidebar_list = self.ui.listView


        # Registry of Logic Types available to the user
        self.available_logics = {
            "Port Search": PortSearchColumn,
            "Function Search": FunctionSearchColumn,
            "Variable Search": VariableSearchColumn,
            "Review Status": ReviewColumn,
            "Static Text": TableColumn,
            "InitColumn": InitColumn,     # Exposed for Customizer
            "CyclicColumn": CyclicColumn, # Exposed for Customizer
            "PortStateColumn": PortStateColumn, # Internal use
            "ResultColumn": LastResultColumn, # Req 7 (Renamed logic, kept key for compatibility)
            "ReleaseResultColumn": ReleaseResultColumn, # Req 8
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
            ("Port State", "PortStateColumn", True),
        ]
        # Issue 1: Track columns that have EVER been part of a reviewed row
        self.permanently_locked_columns = set()
        
        # Track current default cyclicity to detect changes
        self.current_default_cyclicity = "10"
        
        # Track visibility filters for Port State
        self.show_retired = True
        self.show_deleted = True
        
        # Req 8: Metadata is now stored per-model in ArchitectureModel.data_cache
        # We keep a local reference for convenience, but it must be synced.
        self.column_metadata = {}

        # Architecture Manager Setup (Sidebar)
        # Must be initialized BEFORE _rebuild_column_objects because rebuild might read metadata from the active model
        self.model_manager = ArchitectureManager(None) # Path set later
        self.list_model = ArchitectureListModel(self.model_manager)
        self.sidebar_list.setModel(self.list_model)
        
        # Release Manager Setup (Separate)
        self.release_manager = ReleaseManager(None)

        self._rebuild_column_objects()
        self._setup_table_style()
        self._connect_signals()

        # UI Polish: Spacing and Styling
        self.sidebar_list.setSpacing(4)
        
        # Connect Selection
        self.sidebar_list.selectionModel().currentChanged.connect(self.on_model_selection_changed)
        
        # Enable Sidebar Context Menu
        self.sidebar_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar_list.customContextMenuRequested.connect(self.show_sidebar_context_menu)
        
        # Initial Load (Default Model)
        self.load_active_model_to_table()

    def _rebuild_column_objects(self):
        """
        Converts the config tuples (active_config) into actual logic instances
        """
        config = getattr(self, 'active_config', [])
        self.active_columns = []

        for col_data in config:
            name, logic_key = col_data[0], col_data[1].strip()
            visible = col_data[2] if len(col_data) > 2 else None
            
            logic_cls = self.available_logics.get(logic_key, TableColumn)
            
            col_obj = logic_cls(name)
            col_obj.user_visible = visible
            
            # Req 8: Restore initialization state from current model's metadata
            # Note: We can't rely on self.column_metadata being populated yet if called before load
            # It will be updated during load_active_model_to_table or flush.
            # But during _rebuild, we might be using the currently loaded model.
            current_model = self.model_manager.get_active_model()
            if current_model and current_model.data_cache:
                model_meta = current_model.data_cache.get("column_metadata", {})
                if name in model_meta:
                    is_init = model_meta[name].get("is_initialized", False)
                    if hasattr(col_obj, 'is_initialized'):
                        col_obj.is_initialized = is_init
            
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

        if self.table.rowCount() == 0:
            self.table.insertRow(0)
            self._initialize_row_widgets(0)
            
        # 4. Apply Visibility Override (Fix for Issue 1)
        for i, col_obj in enumerate(self.active_columns):
            if col_obj.user_visible is not None:
                self.table.setColumnHidden(i, not col_obj.user_visible)
            
        # 5. Apply Port State Filters
        self.apply_port_state_filters()

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

                expected_val = cyc_col.get_expected_value(current_func_name)
                
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

    def _initialize_row_widgets(self, row, lazy=False):
        """Ensures widgets like the Review dropdown are created for a new row."""
        for col_idx, col_obj in enumerate(self.active_columns):
            # Fetch existing text if available (e.g. when restoring columns)
            text = ""
            item = self.table.item(row, col_idx)
            if item:
                text = item.text()
            
            # Req 8: New Row Logic for ReleaseResultColumns
            # If the column is already initialized, new rows should be "No Result"
            if isinstance(col_obj, ReleaseResultColumn) and getattr(col_obj, 'is_initialized', False):
                if not text:
                     text = "No Result"
                     # Ensure item exists to hold the text
                     if not item:
                         item = QtWidgets.QTableWidgetItem()
                         self.table.setItem(row, col_idx, item)
                     item.setText(text)

            col_obj.on_change(self.table, row, col_idx, text, self, lazy=lazy)

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
            if key not in ["InitColumn", "CyclicColumn", "Review Status", "PortStateColumn"]
        ]

        # Ensure "TC. ID" is always locked to preserve logic and traceability
        self.permanently_locked_columns.add("TC. ID")
        # Lock "Port State"
        self.permanently_locked_columns.add("Port State")

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
        
        # Set current filter states
        dialog.set_filter_states(self.show_retired, self.show_deleted)
        
        if dialog.exec():
            new_config = dialog.get_selected_config()
            new_default_cyclicity = dialog.get_default_cyclicity()
            
            # Retrieve new filter states
            self.show_retired, self.show_deleted = dialog.get_filter_states()
            
            update_existing = False
            
            # Check if default cyclicity changed
            if new_default_cyclicity != self.current_default_cyclicity:
                # Create Custom Dialog
                msg_box = QtWidgets.QMessageBox(self.main_window)
                msg_box.setWindowTitle("Apply Configuration Update?")
                msg_box.setText("The default cyclicity value has been modified. Would you like to synchronize all existing 'Auto' ports with this new configuration?")
                msg_box.setInformativeText("Applying this change to existing entries may impact previous validation results. This action will trigger a re-validation requirement (Purple State) for affected rows to ensure regression integrity.")
                
                # Add Buttons
                apply_all_btn = msg_box.addButton("Apply to all ports", QtWidgets.QMessageBox.ButtonRole.YesRole)
                apply_new_btn = msg_box.addButton("Apply to new ports only", QtWidgets.QMessageBox.ButtonRole.NoRole)
                
                msg_box.exec()
                
                if msg_box.clickedButton() == apply_all_btn:
                    update_existing = True
            
            self.apply_new_columns(new_config, new_default_cyclicity, update_existing)
            
            # Re-apply filters
            self.apply_port_state_filters()

            # Save to temporary file to mark as dirty
            if self.main_window.current_project_file:
                ProjectSaver.save_temp(self.main_window, self.main_window.current_project_file)

    def apply_new_columns(self, column_names, default_cyclicity="10", update_existing_cyclic=False):
        """
        Reconfigures the table columns while trying to preserve existing data.
        'new_config' is a list of (name, logic_type) tuples.
        """
        
        # UI Responsiveness: Helper to keep window alive
        from PyQt6.QtCore import QCoreApplication, Qt
        from .Logic_Loading_Window import LoadingDialog
        
        # Create and show loading dialog (Modal to block interaction but allow painting)
        loading = LoadingDialog(self.main_window)
        loading.ui.lbl_loading_text.setText("Applying changes...")
        loading.setWindowModality(Qt.WindowModality.ApplicationModal)
        loading.show()
        QCoreApplication.processEvents()
        
        # Optimization: Flush current data to the active model's cache
        # This saves the state (including manual overrides) before we wipe the table.
        loading.append_log("Saving current state...")
        self.flush_current_data_to_model()
        QCoreApplication.processEvents()

        # Step 1: Clear the table visually (Switch to empty)
        # This prevents the table from trying to render/calculate layout during reconfiguration
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table.setUpdatesEnabled(True)
        
        # Step 2: Update Configuration
        loading.append_log("Reconfiguring columns...")
        QCoreApplication.processEvents()
        
        self.current_default_cyclicity = default_cyclicity
        self.active_config = column_names
        self._rebuild_column_objects()
        
        # Step 3: Rebuild Table Structure
        self._setup_table_style()
        
        # Step 4: Reload Data from Model (Cache)
        # This handles the restoration into the new column layout automatically.
        # Note: 'load_active_model_to_table' usually runs its own LoadingDialog, 
        # but since we are already in one, we might want to call _load_row_data directly?
        # A: active_model has the data we just flushed.
        # A2: load_active_model_to_table also handles 'active_config' from model? 
        # Wait, the model doesn't store config, the project/controller does.
        # So we just need to get the rows and load them.
        
        current_model = self.model_manager.get_active_model()
        if current_model and current_model.data_cache:
            rows_data = current_model.data_cache.get("rows", [])
            # Sync metadata from model to controller
            self.column_metadata = current_model.data_cache.get("column_metadata", {})
            
            loading.append_log(f"Restoring {len(rows_data)} rows...")
            QCoreApplication.processEvents()
            self._load_row_data(rows_data)
            
        # Req 8: Run initialization logic for any new columns that haven't run yet
        self._run_column_initialization_logic()
        
        # Step 5: Handle Default Cyclicity Updates if requested
        if update_existing_cyclic:
             self._apply_default_cyclicity_update()

        loading.close()

    def _apply_default_cyclicity_update(self):
        """Helper to update existing 'Auto' cyclic ports to new default."""
        for row in range(self.table.rowCount()):
            for col_idx, col_obj in enumerate(self.active_columns):
                if isinstance(col_obj, CyclicColumn):
                     item = self.table.item(row, col_idx)
                     # Only update if NOT user changed (meaning it is Auto)
                     if item and not UserInteractionLogic.is_item_user_changed(item):
                         # Re-trigger on_change to recalculate default
                         col_obj.on_change(self.table, row, col_idx, "", self)
        self.table.blockSignals(False)
        
        loading.append_log("Done.")
        loading.close()

    def _run_column_initialization_logic(self):
        """
        Executes the one-time initialization logic for ReleaseResultColumns.
        Robust Logic:
        - Checks is_initialized flag to prevent overwrite.
        - Reads Port State from Widget OR Item (fallback).
        - Logic:
            - Arch Released + Port Released -> Not Run
            - Ach Released + Port !Released -> Block
            - Arch !Released -> Block (Unless Retired -> No Result)
        """
        current_model = self.model_manager.get_active_model()
        if not current_model:
            return

        arch_state = current_model.status # "Released", "In Work", "Retired"
        port_state_idx = self.get_column_index_by_type("PortStateColumn")
        
        for col_idx, col_obj in enumerate(self.active_columns):
            if isinstance(col_obj, ReleaseResultColumn):
                # No column-level check anymore. We check per row.
                
                # Fetch existing results from cache for ROBUST existence check
                # This fulfills User Req: "check the text value for the speciffic cell from the JSON Data Base"
                cached_results = {}
                if current_model.data_cache and "release_results" in current_model.data_cache:
                    cached_results = current_model.data_cache["release_results"]
                
                col_cached_data = cached_results.get(col_obj.name, [])

                for row in range(self.table.rowCount()):
                    # EXISTENCE CHECK: 
                    # 1. Check Cache (Primary Source of Truth)
                    if row < len(col_cached_data):
                        val = col_cached_data[row]
                        if val and val not in ["", "No Result", "Block"]: 
                             # If we have a concrete value (Passed/Failed/Not Run), preserve it.
                             # Note: We allow "Block" or "No Result" to be re-evaluated if conditions changed?
                             # User said "Not Tested is still rewriting". 
                             # Let's strictly preserve ANY existing data from cache to be safe.
                             continue

                    # 2. Check UI (Fallback for new rows not in cache yet)
                    current_widget = self.table.cellWidget(row, col_idx)
                    current_item = self.table.item(row, col_idx)
                    
                    if current_widget:
                        # If widget exists, it implies initialization happened or user interacted
                        continue
                    if current_item and current_item.text() and current_item.text() != "No Result":
                        # If meaningful text exists
                        continue
                        
                    # --- BUG FIX 2: Robust Port State Reading ---
                        
                    # --- BUG FIX 2: Robust Port State Reading ---
                    port_state = "In Work" # Default fallback
                    
                    if port_state_idx != -1:
                        # 1. Try Widget
                        w = self.table.cellWidget(row, port_state_idx)
                        if w and isinstance(w, QtWidgets.QComboBox):
                            port_state = w.currentText()
                        else:
                            # 2. Try Item Text (Backend Data)
                            item = self.table.item(row, port_state_idx)
                            if item and item.text():
                                port_state = item.text()

                    new_val = "No Result"

                    # Logic Implementation (User Proposed + Correction for 'Block')
                    if arch_state == "Retired":
                         new_val = "No Result"
                    elif port_state in ["Retired", "Deleted"]:
                         new_val = "No Result"
                    elif arch_state in ["Released", "Accepted"]:
                        # User Req: "When the Architecture model is acceped all the results... Not Run"
                        # We treat "Accepted" same as "Released" for logic purposes.
                        if port_state == "Released":
                            new_val = "Not Run"
                        else:
                            new_val = "Block"
                    else:
                        # In Work
                        new_val = "Block"
                            
                    # Apply
                    item = self.table.item(row, col_idx)
                    if not item:
                        item = QtWidgets.QTableWidgetItem()
                        self.table.setItem(row, col_idx, item)
                    
                    # We rely on on_change to create the widget and set the value
                    col_obj.on_change(self.table, row, col_idx, new_val, self)

    def apply_port_state_filters(self):
        """
        Hides or shows rows based on the Port State column and current filters.
        """
        state_col_idx = self.get_column_index_by_type("PortStateColumn")
        if state_col_idx == -1:
            return

        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, state_col_idx)
            if widget and isinstance(widget, QtWidgets.QComboBox):
                state = widget.currentText()
                
                should_hide = False
                if state == "Retired" and not self.show_retired:
                    should_hide = True
                elif state == "Deleted" and not self.show_deleted:
                    should_hide = True
                
                self.table.setRowHidden(row, should_hide)

    def populate_from_parser(self, parser, release_name=None):
        """
        Initializes the matcher when a new ELF/JSON is successfully loaded
        """
        if not parser:
            print("Error: Received empty parser in ArchitectureTabController")
            return

        self.parser = parser
        self.matcher = SymbolMatcher(parser)
        
        # Create the Release Node if name provided
        if release_name:
             try:
                 # Check if exists? If loading JSON, it might exist? 
                 # Logic_New_Project.py prompts for name.
                 # If user enters existing name, create_release will raise error?
                 # Or should we handle it?
                 # Requirements: "5.1 Prompt the user to enter the Release Version"
                 # create_release handles uniqueness by appending? Or raises?
                 # ReleaseManager.create_release raises "Release 'name' already exists".
                 
                 # We should probably catch this or handle it gracefully.
                 # For now, let's try creation.
                 self.release_manager.create_release(release_name, elf_path=str(parser.elf_path))
                 # self.list_model.refresh() # No longer exists on release_manager
             except ValueError as e:
                 # If exists, maybe just switch to it? 
                 # But "New Project" usually implies empty slate? 
                 # Or if loading ELFs into existing project...
                 # Logic_New_Project creates a fresh project usually?
                 # Wait, MainWindow.new_project -> Dialog -> populate
                 # It resets 'current_project_file' to None.
                 # But 'arch_controller' persists?
                 # If we are starting fresh, model_manager might still have data if we didn't reset it.
                 # We probably need to reset model_manager on new project?
                 
                 # Actually, New Project usually implies clearing everything.
                 # But we just reuse the controller.
                 # self.model_manager = ReleaseManager(None) was done in init.
                 # We should wipe it or re-init?
                 
                 print(f"Release creation warning: {e}")
                 # If it exists, find it and select it
                 for i, r in enumerate(self.release_manager.releases):
                     if r.name == release_name:
                         self.release_manager.set_active_release(i)
                         break

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

            # Trigger PortStateColumn as well (since we added has_content logic to it)
            port_state_idx = self.get_column_index_by_type("PortStateColumn")
            if port_state_idx != -1 and port_state_idx != col_idx:
                 self.active_columns[port_state_idx].on_change(self.table, row, port_state_idx, "", self)

            # Fix for Bug 2: Ensure ReleaseResultColumn updates when row gets content
            # Iterate through all columns to find ReleaseResultColumn instances
            for i, col_obj in enumerate(self.active_columns):
                if isinstance(col_obj, ReleaseResultColumn) and i != col_idx:
                    # Retrieve current text to preserve state, or let it default
                    curr_item = self.table.item(row, i)
                    curr_text = curr_item.text() if curr_item else ""
                    col_obj.on_change(self.table, row, i, curr_text, self)

            # Auto-add new row logic
            # Fix for Random Row Addition: Only allow "Input" columns (Search Columns or Static Text) to trigger new row.
            # Output columns (Result, Review, State) should NOT trigger row creation.
            # strict type check for TableColumn ensures we don't accidentally allow subclasses (like ResultColumn)
            if row == self.table.rowCount() - 1 and text != "":
                should_add = False
                if col_idx < len(self.active_columns):
                    col_obj = self.active_columns[col_idx]
                    
                    is_search = isinstance(col_obj, (PortSearchColumn, FunctionSearchColumn, VariableSearchColumn))
                    is_static = type(col_obj) is TableColumn
                    
                    if is_search or is_static:
                        should_add = True
                
                if should_add:
                    new_row = self.table.rowCount()
                    self.table.insertRow(new_row)
                    self._initialize_row_widgets(new_row)
        finally:
            self.table.blockSignals(False)

    def handle_generate(self):
        print("Generation triggered...")

    def get_project_data(self):
        """
        Collects all data required to save the project.
        """
        project_data = {
            "config": self.active_config,
            "settings": {
                "default_cyclicity": self.current_default_cyclicity,
                "show_retired": self.show_retired,
                "show_deleted": self.show_deleted
            },
            # "column_metadata": self.column_metadata, # Removed from Project Level, now in Architecture Level
            "rows": []
        }

        for row in range(self.table.rowCount()):
            row_data = {}
            for col_idx, col_obj in enumerate(self.active_columns):
                cell_info = {}
                
                # Get Item Data
                item = self.table.item(row, col_idx)
                if item:
                    cell_info["text"] = item.text()
                    cell_info["user_changed"] = UserInteractionLogic.is_item_user_changed(item)
                    cell_info["is_purple"] = UserInteractionLogic.is_purple(item)
                    cell_info["last_func"] = UserInteractionLogic.get_last_function(item)
                else:
                    cell_info["text"] = ""
                
                # Get Widget Data
                widget = self.table.cellWidget(row, col_idx)
                if isinstance(widget, QtWidgets.QComboBox):
                    cell_info["widget_text"] = widget.currentText()
                    cell_info["widget_style"] = widget.styleSheet()
                
                row_data[col_obj.name] = cell_info
            
            project_data["rows"].append(row_data)
            
        return project_data

    def load_project_data(self, data):
        """
        Restores the project state from the loaded data.
        Fast Loading Optimization: Splits config/schema loading from row data loading.
        """
        # 1. Restore Settings and Configuration (Schema level)
        settings = data.get("settings", {})
        config = data.get("config", [])
        # self.column_metadata = data.get("column_metadata", {}) # Removed, loaded from Model
        
        # Legacy Support: Metadata is now handled in load_active_model_to_table per model.
        # We do NOT populate self.column_metadata here.
        
        # Determine if we need to rebuild the table schema
        current_config_tuples = [tuple(x) for x in self.active_config]
        new_config_tuples = [tuple(c) for c in config]
        
        rebuild_needed = (current_config_tuples != new_config_tuples) or not self.active_columns
        
        if rebuild_needed:
             self.current_default_cyclicity = settings.get("default_cyclicity", "10")
             self.show_retired = settings.get("show_retired", True)
             self.show_deleted = settings.get("show_deleted", True)
             
             self.active_config = new_config_tuples
             self._rebuild_column_objects()
             
             # Rebuild Table Columns
             self.table.clear()
             self.table.setRowCount(0)
             self._setup_table_style()
        else:
             # Just update simple settings if schema is same
             self.show_retired = settings.get("show_retired", True)
             self.show_deleted = settings.get("show_deleted", True)
        
        # 2. Restore Row Data
        rows = data.get("rows", [])
        self._load_row_data(rows)

    def _load_row_data(self, rows):
        """
        Efficiently loads row data into the existing table schema.
        Clears existing rows but preserves column structure.
        """
        self.table.setUpdatesEnabled(False) # Optimization: Stop Repainting
        self.table.blockSignals(True)
        # Clear existing content but keep headers/columns
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        
        for row_idx, row_data in enumerate(rows):
            # Pass 1: Restore Items (Text & Metadata) first so 'has_content' checks pass
            for col_idx, col_obj in enumerate(self.active_columns):
                cell_info = row_data.get(col_obj.name, {})
                
                # Restore Item Data
                text = cell_info.get("text", "")
                item = self.table.item(row_idx, col_idx)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    self.table.setItem(row_idx, col_idx, item)
                
                item.setText(text)
                
                if cell_info.get("user_changed"):
                    UserInteractionLogic.mark_manual_override(item)
                
                if cell_info.get("is_purple"):
                    UserInteractionLogic.mark_purple(item)
                    
                last_func = cell_info.get("last_func")
                if last_func:
                    UserInteractionLogic.set_last_function(item, last_func)

            # Pass 2: Initialize Widgets (Now that row has content, widgets will be created)
            # Optimization: Use 'lazy=True' to skip expensive search logic during load
            self._initialize_row_widgets(row_idx, lazy=True)

            # Pass 3: Restore Widget State
            for col_idx, col_obj in enumerate(self.active_columns):
                cell_info = row_data.get(col_obj.name, {})
                
                widget_text = cell_info.get("widget_text")
                if widget_text:
                    widget = self.table.cellWidget(row_idx, col_idx)
                    # Note: widget should exist now if _initialize_row_widgets worked
                    if isinstance(widget, QtWidgets.QComboBox):
                        # Handle special cases like "Broken Link" for ReviewColumn
                        if isinstance(col_obj, ReviewColumn) and widget_text == "Broken Link":
                             if widget.findText("Broken Link") == -1:
                                widget.addItem("Broken Link")
                        
                        widget.blockSignals(True)
                        widget.setCurrentText(widget_text)
                        
                        widget_style = cell_info.get("widget_style")
                        if widget_style:
                            widget.setStyleSheet(widget_style)
                        
                        widget.blockSignals(False)

            # Pass 4: explicitly restore logic (colors, side effects)
            self._restore_row_logic(row_idx)

        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True) # Optimization: Resume Repainting
        
        # Batch Refresh Logic
        self.refresh_init_column_state()
        self.refresh_cyclic_column_state()
        
        # Apply filters
        self.apply_port_state_filters()

    def _restore_row_logic(self, row):
        """
        Manually re-triggers the logic (colors, side-effects) for widgets in a row 
        after loading data, ensuring the visual state matches the text content.
        This fixes issues where loaded data appeared 'plain' or uncolored because
        signals were blocked during loading.
        """
        for col_idx, col_obj in enumerate(self.active_columns):
            widget = self.table.cellWidget(row, col_idx)
            if not widget: continue
            
            # Review Column: Re-apply color and effects on other columns
            if isinstance(col_obj, ReviewColumn):
                if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_status_change(self.table, row, col_idx, widget.currentText())
            
            # Port State: Re-apply row visuals (strike-through etc)
            elif isinstance(col_obj, PortStateColumn):
                 if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_state_change(self.table, row, col_idx, widget.currentText(), self)
            
            # Search Columns: Re-calculate color based on percentage if style is missing
            elif isinstance(col_obj, (PortSearchColumn, FunctionSearchColumn, VariableSearchColumn)):
                 if isinstance(widget, QtWidgets.QComboBox):
                     # Logic from ReviewColumn._apply_score_color but generalized
                     text = widget.currentText()
                     import re
                     match = re.search(r'\((\d+)%\)$', text)
                     if match:
                        score = int(match.group(1))
                        color = "#2e8b57" if score >= 80 else "#b8860b" if score >= 60 else "#8b0000"
                        
                        # Respect Review Override
                        status = UserInteractionLogic.get_review_status(self.table, row, self)
                        if status == "Reviewed":
                             color = "#2e8b57"
                        elif status == "Broken Link":
                             color = "#483d8b"
                        
                        widget.setStyleSheet(f"color: {color}; font-weight: bold;")

            # Fix: Restore Result Column Colors (Since signals were blocked)
            elif isinstance(col_obj, (ReleaseResultColumn, LastResultColumn)):
                 if isinstance(widget, QtWidgets.QComboBox):
                     col_obj._handle_state_change(self.table, row, col_idx, widget.currentText(), self)                             
    def show_sidebar_context_menu(self, pos):
        # Open the Release Selection Window
        from UI.Dialog_Release_Selection import ReleaseSelectionDialog
        
        dialog = ReleaseSelectionDialog(self.release_manager, self.main_window)
        if dialog.exec():
            # If user selected a release (clicked Select/Load), dialog sets 'selected_release_index'
            if dialog.selected_release_index != -1:
                 # Switch to it
                 new_release = self.release_manager.set_active_release(dialog.selected_release_index)
                 
                 # RELOAD ELF DATA
                 if new_release and new_release.data_cache:
                      elf_data = new_release.data_cache.get("database", {})
                      if elf_data:
                           ProjectSaver._populate_parser(self.main_window, elf_data)
                           print(f"Switched to Release: {new_release.name} and loaded ELF data.")
                      else:
                           # If no data, maybe effectively unload parser?
                           pass
                 
                 # Refresh table only if needed? 
                 # We probably want to update search completions at least.
                 if self.main_window.parser:
                      self.populate_from_parser(self.main_window.parser)
                 
            # Also if 'Deep Search' was enabled, we might trigger something?
            # For now just handle switch.
        
        self.list_model.refresh()
        self.sidebar_list.update()

    def on_model_selection_changed(self, current, previous):
        if not current.isValid():
            return
            
        real_index = current.row() # List model is now flat, so row is index
        # Fix: ArchitectureManager uses active_model_index, not active_release_index
        if real_index == self.model_manager.active_model_index:
            return
            
        # 1. Save current table data to the OLD active model
        self.flush_current_data_to_model()
        
        # 2. Set new active model
        # Fix: ArchitectureManager uses set_active_model
        self.model_manager.set_active_model(real_index)
        
        # 3. Load data
        self.load_active_model_to_table()

    # Removed duplicate flush_current_data_to_model (was lines 1021-1038)


    def show_sidebar_context_menu(self, pos):
        # Open the Manager Window
        from UI.Dialog_Architecture_Manager import ArchitectureManagerDialog
        
        # FIX: Save current data before opening manager, preventing data loss on reload
        self.flush_current_data_to_model()
        
        # We can also add a "Manage Models..." action to a menu if we want to keep it subtle,
        # but user asked for "window similar to Customize Table Columns... triggered on right click".
        # So right click -> Immediate Window? Or Right Click -> Menu "Manage Models" -> Window?
        # User said: "triggered on right click ... not the right click menu that is currently integrated"
        # The Customizer is triggered by right clicking the HEADER.
        # This sidebar menu is triggered by right clicking the SIDEBAR.
        
        dialog = ArchitectureManagerDialog(self.model_manager, self.main_window)
        if dialog.exec():
            # Refresh list if models changed
            self.list_model.refresh()
            # If active model was deleted or changed, we might need to reload?
            # Start simple: reload table from whatever is now active
            self.load_active_model_to_table()

    def load_active_model_to_table(self):
        """Loads the currently active ArchitectureModel into the table"""
        current_model = self.model_manager.get_active_model()
        if not current_model:
            # Clear table if no models?
            # Or create default? Manager usually ensures at least one.
            return

        self.main_window.setWindowTitle(f"Architecture Testing Tool - {current_model.name}")
        
        # UI: Helpers
        from PyQt6.QtCore import QCoreApplication, Qt
        from .Logic_Loading_Window import LoadingDialog

        loading = LoadingDialog(self.main_window)
        loading.ui.lbl_loading_text.setText(f"Loading {current_model.name}...")
        # loading.show() # Optional, might be too flashy for quick switches
        QCoreApplication.processEvents()

        # Get rows from the model's cache
        rows_data = []
        if current_model.data_cache:
            rows_data = current_model.data_cache.get("rows", [])
        elif current_model.file_path and os.path.exists(current_model.file_path):
             # Just in case cache is empty but file exists (shouldn't happen with Manager)
             # The manager preload should have handled this? 
             # Or we load on demand? Manager.preload_all_models() is called on project load.
             pass

        # FIX: Restore Project/Model Configuration (Phantom Columns Fix)
        # If the model has a saved configuration, we must restore it to the controller.
        # Otherwise, the controller keeps the previous model's config, leading to schema drift.
        model_config = current_model.data_cache.get("config", [])
        if model_config:
            # Only update if different (optimization)
            # But deep comparison is safe enough
            if self.active_config != model_config:
                print(f"DEBUG: Restoring configuration for {current_model.name}")
                self.active_config = model_config
                self._rebuild_column_objects()
                self._setup_table_style()
        
        if not rows_data:
             # If empty, maybe it's a new model?
             # Clear table
             self.table.setRowCount(0)
             # Fix: Ensure at least one empty row for editing!
             self.table.insertRow(0)
             self._initialize_row_widgets(0)
             # Ensure metadata is clear if new
             self.column_metadata = {}
        else:
            # Sync metadata from model to controller (Legacy support or future use)
            self.column_metadata = current_model.data_cache.get("column_metadata", {})

            # Legacy Support: Check for uninitialized ReleaseResultColumns that have data in loaded rows
            for col_idx, col_obj in enumerate(self.active_columns):
                if isinstance(col_obj, ReleaseResultColumn):
                    if col_obj.name not in self.column_metadata:
                         # Check if any row has data for this column
                         has_data = False
                         for row_dict in rows_data:
                             col_data = row_dict.get(col_obj.name, {})
                             if col_data.get("text") or col_data.get("widget_text"):
                                 has_data = True
                                 break
                         
                         if has_data:
                             # Mark as initialized to prevent overwrite
                             col_obj.is_initialized = True
                             self.column_metadata[col_obj.name] = {"is_initialized": True}
                             
                             # Update model cache immediately to prevent dataloss if flush happens later
                             if "column_metadata" not in current_model.data_cache:
                                 current_model.data_cache["column_metadata"] = {}
                             current_model.data_cache["column_metadata"][col_obj.name] = {"is_initialized": True}
            
            # Optimization: Directly load rows into existing schema
            self._load_row_data(rows_data)
            
            # --- IMPLEMENTATION: Restore from Result Dictionary ---
            # If "release_results" exists, we override/populate the result columns from it.
            # This is the "Primary Source of Truth" for results if present.
            release_results = current_model.data_cache.get("release_results", {})
            if release_results:
                for col_idx, col_obj in enumerate(self.active_columns):
                    if isinstance(col_obj, ReleaseResultColumn) and col_obj.name in release_results:
                        loading.append_log(f"Restoring results for {col_obj.name}...")
                        result_list = release_results[col_obj.name]
                        
                        # Apply to table
                        for row, val in enumerate(result_list):
                            if row >= self.table.rowCount(): break # Safety
                            
                            # Update visual state using on_change (handles widget creation/coloring/item text)
                            # We pass the value even if empty to ensure formatting
                            if val:
                                col_obj.on_change(self.table, row, col_idx, val, self)
            
            # Run Logic (skips if initialized OR if data exists)
            self._run_column_initialization_logic()
            
            # Restore filters
            self.apply_port_state_filters()

    def flush_current_data_to_model(self):
        """Saves current table rows into the active ArchitectureModel object (cached or file)"""
        current_model = self.model_manager.get_active_model()
        if not current_model:
            return

        # Get rows data from existing method
        # We only want 'rows' part usually, but let's get project data structure
        full_data = self.get_project_data()
        
        # Inject current metadata (Model Scope)
        full_data["column_metadata"] = self.column_metadata
        
        # --- IMPLEMENTATION: Result Dictionary ---
        # Extract data from ReleaseResultColumns into a separate dictionary
        # dictionary of lists: { "ColumnName": ["Val1", "Val2", ...] }
        # This ensures we have a clean source of truth separate from "rows" structure if needed,
        # and fulfills user request for explicit dictionary storage.
        
        # Merge Logic: Load existing first (if available in cache) to prevent overwrite
        existing_results = current_model.data_cache.get("release_results", {}) if current_model.data_cache else {}
        release_results = {}
        
        for col_idx, col_obj in enumerate(self.active_columns):
            if isinstance(col_obj, ReleaseResultColumn):
                col_data = []
                # Check if we have existing data for this column
                existing_col_data = existing_results.get(col_obj.name, [])
                
                for row in range(self.table.rowCount()):
                    # Get value (Widget > Item > Empty)
                    val = ""
                    widget = self.table.cellWidget(row, col_idx)
                    item = self.table.item(row, col_idx)
                    
                    if widget and isinstance(widget, QtWidgets.QComboBox):
                        val = widget.currentText()
                    elif item:
                        val = item.text()
                    
                    # SMART MERGE: 
                    # If current table value is "No Result" or "Not Run" AND we have a valid previous value, KEEP PREVIOUS.
                    # User Req: "Also the Not Tested is still rewriting the dictionary"
                    # We treat "Not Run" (default) and "No Result" (disabled) as 'weak' states compared to 'Pas/Fail'.
                    if val in ["No Result", "Not Run", "Block"] and row < len(existing_col_data):
                        prev_val = existing_col_data[row]
                        if prev_val in ["Passed", "Failed", "Warning"]:
                            print(f"Preserving '{prev_val}' over '{val}' for {col_obj.name} Row {row}")
                            val = prev_val
                    
                    col_data.append(val)
                release_results[col_obj.name] = col_data
        
        full_data["release_results"] = release_results

        # CLEANUP: Remove Layout/Settings from Model Data
        # User Req 1: "In the Architecture JSONs the Layout is also saved -> Layout should only be saved in the Layout.json"
        if "config" in full_data:
            del full_data["config"]
        if "settings" in full_data:
            del full_data["settings"]
        
        current_model.data_cache = full_data
        
        current_model.data_cache = full_data
        
        # Debug Trace
        print(f"DEBUG: Flushed data for '{current_model.name}' (File: {current_model.file_path}). Rows: {len(full_data.get('rows', []))}")
        
        if current_model.file_path:
             # Just write rows to its specific file to be safe against crash
             try:
                 import json
                 with open(current_model.file_path, 'w') as f:
                     json.dump(full_data, f, indent=4)
                 print(f"DEBUG: Successfully wrote file {current_model.file_path}")
             except Exception as e:
                 print(f"Auto-save model failed: {e}")

    def set_project_path(self, path):
        """Called by ProjectSaver or Main when project path is established/changed."""
        # Update both managers
        self.model_manager.set_project_path(path)
        self.release_manager.set_project_path(path)
        
        # Flush current to the new path immediately
        self.flush_current_data_to_model()

    def create_result_columns_for_release(self, release):
        """
        Req 7: Creates 'Last Result' and 'Release_X_Result' columns.
        Populates them based on current Port State.
        """
        if not release:
            return

        last_res_name = "Last Result"
        rel_res_name = f"Release_{release.name}_Result"
        
        # Check if columns exist in config
        current_names = [c[0] for c in self.active_config]
        
        if rel_res_name in current_names:
             # User Req 2: "The result column should be generated only once... we should add a warning"
             # Warn and Return
             QtWidgets.QMessageBox.warning(self.main_window, "Column Exists", 
                                           f"Result column '{rel_res_name}' already exists.\nCannot add duplicate.")
             return

        # 1. Save Current State (Flush)
        # This ensures any changes in current cells are saved before we reload
        self.flush_current_data_to_model()

        # 2. Update Configuration
        self.active_config.append((rel_res_name, "ReleaseResultColumn", True))
        
        if last_res_name not in current_names:
            # Insert Last Result if missing
            self.active_config.append((last_res_name, "LastResultColumn", True))

        # 3. Rebuild Schema Objects
        self._rebuild_column_objects()
        
        # 3b. Update Visual Table Schema (CRITICAL FIX)
        # load_active_model_to_table does NOT update column count/headers. 
        # We must do it here because we changed active_config.
        self._setup_table_style()
        
        # 4. FULL RELOAD (User Req: "manual reload... when the release column is created")
        # This calls setup_table_style, loads data, and runs initialization logic cleanly.
        self.load_active_model_to_table()
        
        # self.table.blockSignals(False) # load_active_model_to_table handles signals
        # self.table.viewport().update()

        self.table.blockSignals(False)
        self.table.viewport().update()

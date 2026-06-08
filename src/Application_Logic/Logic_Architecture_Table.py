from PyQt6 import QtWidgets, QtCore, QtGui
import logging
import os
from .Logic_Project_Saving import ProjectSaver

logger = logging.getLogger(__name__)
from .Logic_Symbol_Matcher import SymbolMatcher
from .Logic_Column_Customizer import ColumnCustomizer
from .Logic_Column_Types import TableColumn, PortSearchColumn, FunctionSearchColumn, VariableSearchColumn, ReviewColumn, InitColumn, CyclicColumn, PortStateColumn, LastResultColumn, ReleaseResultColumn, LinkColumn
from .Logic_User_Interaction import UserInteractionLogic
from .Logic_Architecture_Models import ArchitectureManager, ArchitectureListModel
from .Logic_Release_Manager import ReleaseManager
from UI.Dialog_Architecture_Edit import ArchitectureEditDialog
from UI.Dialog_Restore_Model import RestoreModelDialog
from .Logic_Architecture_IO import ArchitectureIOMixin
from .Logic_Architecture_Baseline import ArchitectureBaselineMixin
from .Logic_Architecture_Import import ArchitectureImportMixin


class ArchitectureTabController(ArchitectureIOMixin, ArchitectureBaselineMixin, ArchitectureImportMixin):
    """
    Handles all logic related to the Architecture Validation Tab
    """

    def __init__(self, main_window):
        self.main_window = main_window # Store the actual QMainWindow
        self.ui = main_window.ui # Get the UI components from it
        self.table = self.ui.Architecture_Table
        self.sidebar_list = self.ui.listView
        self.matcher = None

        # Debounce timer: fires 750 ms after the last cell edit in immediate mode
        self._autosave_timer = QtCore.QTimer()
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(750)
        self._autosave_timer.timeout.connect(self._do_autosave)

        # Dirty-row tracking: set of row indices changed since last save
        self._dirty_rows: set = set()
        self._row_snapshots: dict = {}
        # When True a structural change (row add/delete/reorder) requires a full flush
        self._full_flush_needed: bool = False
        # Suppress the sectionResized handler while widths are applied programmatically
        self._suppress_resize_save: bool = False
        # Set when a manual resize needs the column layout persisted on next autosave
        self._layout_dirty: bool = False


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
            "Last Result": LastResultColumn, # User Req 3: called "Last Result" (refactored from ResultColumn)
            "ReleaseResultColumn": ReleaseResultColumn, # Req 8
            "Link": LinkColumn,
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
        self.show_deleted = False
        
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

        # Ensure splitter handles are visible, easily grabbable, and non-collapsible
        self.ui.splitter.setHandleWidth(8)
        self.ui.splitter.setCollapsible(0, False)
        self.ui.splitter.setCollapsible(1, False)
        self.ui.splitter.setSizes([1400, 360])
        self.ui.splitter.setStyleSheet("""
            QSplitter::handle {
                background: #444444;
            }
            QSplitter::handle:hover {
                background: #555555;
            }
        """)

        self._rebuild_column_objects()
        self._setup_table_style()
        self._connect_signals()

        # UI Polish: Spacing and Styling — larger, easier-to-click model rows
        self.sidebar_list.setSpacing(4)
        self.sidebar_list.setStyleSheet("""
            QListView::item {
                padding: 6px 8px;
                font-size: 13px;
            }
        """)

        # Connect Selection
        self.sidebar_list.selectionModel().currentChanged.connect(self.on_model_selection_changed)
        
        # Enable Sidebar Context Menu
        self.sidebar_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar_list.customContextMenuRequested.connect(self.show_sidebar_context_menu)
        
        # Initial Load (Default Model)
        self.load_active_model_to_table()

        # Baseline buttons
        self.btn_create_baseline = QtWidgets.QPushButton(parent=self.ui.SideBar_Architecture)
        self.btn_create_baseline.setObjectName("btn_create_baseline")
        self.btn_create_baseline.setText("Create Baseline")
        self.btn_create_baseline.clicked.connect(self.handle_create_baseline)
        self.ui.verticalLayout.addWidget(self.btn_create_baseline)

        self.btn_load_baseline = QtWidgets.QPushButton(parent=self.ui.SideBar_Architecture)
        self.btn_load_baseline.setObjectName("btn_load_baseline")
        self.btn_load_baseline.setText("Load Baseline")
        self.btn_load_baseline.clicked.connect(self.handle_load_baseline)
        self.ui.verticalLayout.addWidget(self.btn_load_baseline)

        self.btn_exit_baseline = QtWidgets.QPushButton(parent=self.ui.SideBar_Architecture)
        self.btn_exit_baseline.setObjectName("btn_exit_baseline")
        self.btn_exit_baseline.setText("Exit Baseline View")
        self.btn_exit_baseline.setStyleSheet("background-color: #e01b24; color: white; font-weight: bold;")
        self.btn_exit_baseline.clicked.connect(self.handle_exit_baseline)
        self.btn_exit_baseline.setVisible(False)
        self.ui.verticalLayout.addWidget(self.btn_exit_baseline)

    def set_project_db(self, db):
        """Wire all sub-managers to the open ProjectDatabase."""
        self._db = db
        self.model_manager.set_db(db)
        self.release_manager.set_db(db)
        if hasattr(self.main_window, 'history_manager') and self.main_window.history_manager:
            self.main_window.history_manager.set_db(db)

    def sanitize_column_config(self, config):
        """Sanitizes configuration by demoting manual or invalid ReleaseResultColumn/Last Result columns to Static Text."""
        sanitized = []
        for item in config:
            if not item or len(item) < 2:
                sanitized.append(item)
                continue
            
            # Convert to list to allow item assignment
            item_list = list(item)
            name, l_type = item_list[0], item_list[1]
            
            if l_type == "ReleaseResultColumn":
                # A valid ReleaseResultColumn must start with "Release_" and end with "_Result"
                if not (name.startswith("Release_") and name.endswith("_Result")):
                    item_list[1] = "Static Text"
            elif l_type == "Last Result":
                # A valid Last Result column must be named "Last Result"
                if name != "Last Result":
                    item_list[1] = "Static Text"
                    
            sanitized.append(tuple(item_list) if isinstance(item, tuple) else item_list)
        return sanitized

    @staticmethod
    def default_column_config():
        """The default column schema, used for new models and as the Inc-04
        fallback when a loaded model/release has no persisted column schema."""
        return [
            ("TC. ID", "Static Text", True),
            ("Input Port", "Port Search", True), ("Input Port (Match)", "Static Text", True), ("Input Port (Init)", "InitColumn", None), ("Input Port (Cyclic)", "CyclicColumn", None),
            ("Mapped Func", "Function Search", True), ("Mapped Func (Match)", "Static Text", True), ("Mapped Func (Init)", "InitColumn", None), ("Mapped Func (Cyclic)", "CyclicColumn", None),
            ("Mapped Parameter", "Variable Search", True), ("Mapped Parameter (Match)", "Static Text", True),
            ("Review Status", "Review Status", True),
            ("Port State", "PortStateColumn", True),
        ]

    def _rebuild_column_objects(self):
        """
        Converts the config tuples (active_config) into actual logic instances
        """
        self.active_config = self.sanitize_column_config(self.active_config)
        if not self.active_config:
            # Inc-04: a model/release with no persisted column schema must still
            # render the full default column set, never an empty/column-less table.
            self.active_config = self.default_column_config()
        config = getattr(self, 'active_config', [])
        self.active_columns = []

        for col_data in config:
            name, logic_key = col_data[0], col_data[1].strip()
            visible = col_data[2] if len(col_data) > 2 else None
            width = col_data[3] if len(col_data) > 3 else None
            
            logic_cls = self.available_logics.get(logic_key, TableColumn)
            
            if width is not None:
                col_obj = logic_cls(name, width=width)
            else:
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

        # Suppress resize persistence while we apply widths/visibility programmatically;
        # otherwise these calls would clobber the saved widths via on_column_resized.
        self._suppress_resize_save = True
        try:
            # 2. Apply dynamic widths and modes
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(50)

            for i, col_obj in enumerate(self.active_columns):
                self.table.setColumnWidth(i, col_obj.width)
                header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeMode.Interactive)

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
        finally:
            self._suppress_resize_save = False

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
        old_state = self.table.blockSignals(True)
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

        self.table.blockSignals(old_state)

    def refresh_cyclic_column_state(self):
        """
        Master logic for the Cyclic column.
        Parses function names for 'Cyclic' (10) or 'XXms' (XX).
        Follows the same override/purple logic as InitColumn.
        """
        old_state = self.table.blockSignals(True)
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

        self.table.blockSignals(old_state)

    def _initialize_row_widgets(self, row, lazy=False, row_data=None):
        """Ensures widgets like the Review dropdown are created for a new row."""
        for col_idx, col_obj in enumerate(self.active_columns):
            # Fetch existing text if available (e.g. when restoring columns)
            text = ""
            if row_data and col_obj.name in row_data:
                cell_info = row_data[col_obj.name]
                text = cell_info.get("widget_text") or cell_info.get("text", "")
            else:
                item = self.table.item(row, col_idx)
                if item:
                    text = item.text()
            
            # Req 8: New Row Logic for ReleaseResultColumns
            # If the column is already initialized, new rows should be "No Result"
            if isinstance(col_obj, ReleaseResultColumn) and getattr(col_obj, 'is_initialized', False):
                if not text:
                     text = "No Result"
                     # Ensure item exists to hold the text
                     item = self.table.item(row, col_idx)
                     if not item:
                          item = QtWidgets.QTableWidgetItem()
                          self.table.setItem(row, col_idx, item)
                     item.setText(text)

            col_obj.on_change(self.table, row, col_idx, text, self, lazy=lazy)

            # If view-only, disable the newly created cell widget and make item non-editable.
            # ReleaseResultColumn manages its own locking via on_change — skip it here so
            # a baseline lock applied above isn't immediately overridden.
            is_baseline = hasattr(self, 'btn_exit_baseline') and not self.btn_exit_baseline.isHidden()
            edit_mode = getattr(self.main_window, 'edit_mode', True) and not is_baseline
            widget = self.table.cellWidget(row, col_idx)
            if widget and not isinstance(col_obj, ReleaseResultColumn):
                widget.setEnabled(edit_mode)
            item = self.table.item(row, col_idx)
            if item:
                if not edit_mode:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                elif not isinstance(col_obj, ReleaseResultColumn):
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        self.hook_comboboxes()

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

        # Listen for focus/clicks to stash pre-edit values (Feature 5)
        self.table.currentCellChanged.connect(self.on_current_cell_changed)
        self.table.cellPressed.connect(self.on_cell_pressed)

        self.table.horizontalHeader().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_column_customizer)

        # Persist manual column resizes so they survive customizer/rebuilds and saves
        self.table.horizontalHeader().sectionResized.connect(self.on_column_resized)

    def on_column_resized(self, logical_index, old_size, new_size):
        """
        Persist a user-driven column resize into the active config so it survives
        rebuilds (e.g. opening the column customizer) and is saved with the project.
        """
        if self._suppress_resize_save:
            return
        if new_size <= 0:  # ignore hide-driven 0-width events
            return
        if logical_index < 0 or logical_index >= len(self.active_columns):
            return

        self.active_columns[logical_index].width = new_size

        # Mirror the width into active_config as the 4th tuple element.
        if logical_index < len(self.active_config):
            entry = list(self.active_config[logical_index])
            while len(entry) < 4:
                entry.append(None)
            entry[3] = new_size
            self.active_config[logical_index] = tuple(entry)

        # The column layout (widths) must be persisted on the next autosave;
        # autosave otherwise only writes row data, so resizes would be lost on
        # any in-session reload (they only reached the DB on a full save before).
        self._layout_dirty = True
        if getattr(self.main_window, 'current_project_file', None):
            self._autosave_timer.start()

    def on_current_cell_changed(self, row, col, prev_row, prev_col):
        if row >= 0 and col >= 0:
            self._pre_edit_row = row
            self._pre_edit_col = col
            self._pre_edit_value = self.get_cell_value(row, col)
        else:
            self._pre_edit_row = -1
            self._pre_edit_col = -1
            self._pre_edit_value = ""

    def on_cell_pressed(self, row, col):
        if row >= 0 and col >= 0:
            self._pre_edit_row = row
            self._pre_edit_col = col
            self._pre_edit_value = self.get_cell_value(row, col)

    def _cell_of_widget(self, widget):
        """Resolve a cell widget's CURRENT (row, col).

        Indices captured when a widget was created go stale the moment rows are
        inserted/deleted/reordered above it, which used to make combobox edits
        dirty-mark and log the wrong row. We resolve the position live instead:
        a fast indexAt() probe with an authoritative linear-scan fallback.
        Returns (-1, -1) if the widget is no longer in the table.
        """
        idx = self.table.indexAt(widget.geometry().center())
        if idx.isValid() and self.table.cellWidget(idx.row(), idx.column()) is widget:
            return idx.row(), idx.column()
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                if self.table.cellWidget(r, c) is widget:
                    return r, c
        return -1, -1

    def _hook_one_combobox(self, combo):
        """Connect a single combobox's change handler exactly once."""
        if hasattr(combo, "_hooked"):
            return
        combo._hooked = True

        def handler(new_text, combo=combo):
            if self.table.signalsBlocked() or combo.signalsBlocked():
                return
            # Resolve the row/col live — the combo may have moved since hooking.
            r, c = self._cell_of_widget(combo)
            if r == -1:
                return
            old_val = getattr(self, "_pre_edit_value", "")
            pre_row = getattr(self, "_pre_edit_row", -1)
            pre_col = getattr(self, "_pre_edit_col", -1)
            if pre_row != r or pre_col != c:
                old_val = ""
            if old_val != new_text:
                col_name = self.active_columns[c].name if c < len(self.active_columns) else f"Column {c}"
                self._mark_row_dirty(r)
                self.handle_table_cell_change(r, col_name, old_val, new_text)
                self._pre_edit_row = r
                self._pre_edit_col = c
                self._pre_edit_value = new_text

        combo.currentTextChanged.connect(handler)

    def _hook_comboboxes_in_row(self, row):
        """Hook any unhooked comboboxes in a single row (cheap, used on edits)."""
        if row < 0 or row >= self.table.rowCount():
            return
        for col in range(self.table.columnCount()):
            widget = self.table.cellWidget(row, col)
            if isinstance(widget, QtWidgets.QComboBox):
                self._hook_one_combobox(widget)

    def hook_comboboxes(self):
        """Finds all QComboBoxes in the table and hooks their changes for history and auto-save."""
        for row in range(self.table.rowCount()):
            self._hook_comboboxes_in_row(row)

    def _persist_column_layout(self):
        """
        Write the current column layout (incl. widths) to the DB.

        Syncs every visible column's live width into active_config first so a
        single resize doesn't reset the other columns to their defaults. Hidden
        columns report width 0, so their previously stored width is kept.
        """
        db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
        if not db or not db.is_open:
            return
        for i, col_obj in enumerate(self.active_columns):
            if i >= len(self.active_config):
                continue
            w = self.table.columnWidth(i)
            if w <= 0:
                continue  # hidden column — preserve the stored width
            col_obj.width = w
            entry = list(self.active_config[i])
            while len(entry) < 4:
                entry.append(None)
            entry[3] = w
            self.active_config[i] = tuple(entry)
        db.save_column_layout(self.active_config)
        db.commit()

    def _do_autosave(self):
        """Fired by the debounce timer — incremental save for dirty rows, full flush for structural changes."""
        project_file = getattr(self.main_window, 'current_project_file', None)
        if not project_file:
            return
        if self._layout_dirty:
            self._persist_column_layout()
            self._layout_dirty = False
        if self._full_flush_needed or not self._dirty_rows:
            # Full flush path (structural change or first save)
            ProjectSaver.save_temp(self.main_window, project_file)
            self._dirty_rows.clear()
            self._full_flush_needed = False
        else:
            # Incremental path: only persist rows that changed
            self._flush_dirty_rows_to_db()
            # Touch .dirty flag
            try:
                with open(project_file + ".dirty", 'w'):
                    pass
            except OSError:
                pass

    def flush_pending_edits(self):
        """Finding M: synchronously persist any pending (debounced) table edits and
        the active release's in-memory data_cache. Call this BEFORE switching the
        active release, so a fast release switch (within the 750 ms autosave
        debounce) can never discard unsaved edits."""
        try:
            if self._autosave_timer.isActive():
                self._autosave_timer.stop()
                self._do_autosave()
        except Exception:
            logger.exception("flush_pending_edits: autosave flush failed")
        try:
            self.release_manager.flush_active_release_data()
        except Exception:
            logger.exception("flush_pending_edits: release-data flush failed")

    def _flush_dirty_rows_to_db(self):
        """Serialize only dirty rows and upsert them — avoids a full table scan."""
        current_model = self.model_manager.get_active_model()
        if not current_model or current_model.id is None:
            return
        db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
        if not db or not db.is_open:
            return

        from .Logic_User_Interaction import UserInteractionLogic
        dirty = set(self._dirty_rows)  # snapshot
        rows_to_upsert = {}
        for row_idx in dirty:
            if row_idx >= self.table.rowCount():
                continue
            row_data = {}
            for col_idx, col_obj in enumerate(self.active_columns):
                cell_info = {}
                item = self.table.item(row_idx, col_idx)
                if item:
                    cell_info["text"] = item.text()
                    cell_info["user_changed"] = UserInteractionLogic.is_item_user_changed(item)
                    cell_info["is_purple"] = UserInteractionLogic.is_purple(item)
                    cell_info["last_func"] = UserInteractionLogic.get_last_function(item)
                else:
                    cell_info["text"] = ""
                widget = self.table.cellWidget(row_idx, col_idx)
                if isinstance(widget, QtWidgets.QComboBox):
                    cell_info["widget_text"] = widget.currentText()
                    cell_info["widget_style"] = widget.styleSheet()
                row_data[col_obj.name] = cell_info

            rows_to_upsert[row_idx] = row_data
            # Keep model cache in sync
            if current_model.data_cache and "rows" in current_model.data_cache:
                cache_rows = current_model.data_cache["rows"]
                while len(cache_rows) <= row_idx:
                    cache_rows.append({})
                cache_rows[row_idx] = row_data

        if rows_to_upsert:
            db.upsert_model_rows_batch(current_model.id, rows_to_upsert)
        db.commit()

        # Update cache so UI refresh is accurate
        current_model.data_cache["rows"] = db.get_model_rows(current_model.id)

        self._dirty_rows.clear()
        # Snapshots are intentionally NOT cleared here — they must survive autosave
        # so that discard_dirty_rows() can still revert to pre-edit state.
        # Snapshots are cleared only on explicit user save or model switch.
        
    def _mark_row_dirty(self, row: int):
        """Marks a row as dirty and captures a snapshot for discarding changes if needed."""
        if row not in self._dirty_rows:
            if getattr(self, '_row_snapshots', None) is not None and row not in self._row_snapshots:
                db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
                active = self.model_manager.get_active_model()
                if db and active and active.id is not None:
                    self._row_snapshots[row] = db.get_model_row(active.id, row)
            self._dirty_rows.add(row)

    def discard_dirty_rows(self):
        if getattr(self, '_row_snapshots', None) is None or not self._row_snapshots:
            return
        db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
        active = self.model_manager.get_active_model()
        if not db or not active or active.id is None:
            return
        db.upsert_model_rows_batch(active.id, self._row_snapshots)
        db.commit()
        self._dirty_rows.clear()
        self._row_snapshots.clear()
        self._full_flush_needed = False

    def handle_table_cell_change(self, row, col_name, old_val, new_val):
        """Logs changes to history and triggers debounced auto-save if in immediate mode."""
        if not old_val.strip() and not new_val.strip():
            return

        model_name = ""
        current_model = self.model_manager.get_active_model()
        if current_model:
            model_name = current_model.name

        input_port_val = ""
        input_port_col_idx = -1
        for idx, col in enumerate(self.active_columns):
            if col.name == "Input Port":
                input_port_col_idx = idx
                break
        if input_port_col_idx != -1:
            input_port_val = self.get_cell_value(row, input_port_col_idx)

        if not input_port_val.strip():
            input_port_val = "N/A"

        desc = f"Row {row + 1} -> {input_port_val} -> {col_name} -> {old_val} -> {new_val}"
        if hasattr(self.main_window, 'history_manager') and self.main_window.history_manager:
            self.main_window.history_manager.add_entry(desc, model_name)

        # Debounced immediate auto-save: restart the 750 ms timer on every edit
        if getattr(self.main_window, 'auto_save_interval', 'immediate') == 'immediate':
            if getattr(self.main_window, 'current_project_file', None):
                self._autosave_timer.start()

    def open_column_customizer(self, pos):
        """Opens the drag-and-drop dialog and updates table columns."""
        if not getattr(self.main_window, 'edit_mode', True):
            return
        try:
            self._open_column_customizer_impl(pos)
        except Exception as e:
            import traceback
            QtWidgets.QMessageBox.critical(
                self.main_window, "Column Customizer Error",
                f"An error occurred while opening the column editor:\n\n{e}\n\n"
                + traceback.format_exc()
            )

    def _open_column_customizer_impl(self, pos):
        # Issue 3: Init and Cyclic columns should not be presented as individual types
        # Filter them out of the options passed to the UI
        logic_options = [
            key for key in self.available_logics.keys()
            if key not in ["InitColumn", "CyclicColumn", "Review Status", "PortStateColumn", "ReleaseResultColumn", "Last Result"]
        ]

        # Rebuild locked columns fresh each time — never accumulate across calls
        self.permanently_locked_columns = {"TC. ID", "Port State"}

        # Issue 1: Identify locked columns (rows that are Reviewed OR were previously reviewed)
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
            
            # Close and delete customizer dialog immediately to release modal grab
            dialog.close()
            dialog.deleteLater()
            QtWidgets.QApplication.processEvents()
            
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

            # Mark dirty immediately after column customization
            if getattr(self.main_window, 'current_project_file', None):
                self._autosave_timer.start()

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
        if self.main_window and self.main_window.isVisible():
            loading.show()
            QCoreApplication.processEvents()
        
        try:
            # Optimization: Flush current data to the active model's cache
            # This saves the state (including manual overrides) before we wipe the table.
            loading.append_log("Saving current state...")
            self.flush_current_data_to_model()
            QCoreApplication.processEvents()

            # Step 1: Clear the table visually (Switch to empty)
            # This prevents the table from trying to render/calculate layout during reconfiguration
            self.table.blockSignals(True)
            self.table.setUpdatesEnabled(False)
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)
            
            # Step 2: Update Configuration
            loading.append_log("Reconfiguring columns...")
            QCoreApplication.processEvents()
            
            self.current_default_cyclicity = default_cyclicity
            self.active_config = column_names
            self._rebuild_column_objects()
            
            # Step 3: Rebuild Table Structure
            self.table.blockSignals(True)
            self._setup_table_style()
            self.table.blockSignals(False)
            
            # Step 4: Reload Data from Model (Cache)
            current_model = self.model_manager.get_active_model()
            if current_model and current_model.data_cache:
                rows_data = current_model.data_cache.get("rows", [])
                # Sync metadata from model to controller
                self.column_metadata = current_model.data_cache.get("column_metadata", {})
                
                loading.append_log(f"Restoring {len(rows_data)} rows...")
                QCoreApplication.processEvents()
                self._load_row_data(rows_data)
                
                # --- Restore from Result Dictionary (Bug 1 Fix) ---
                release_results = current_model.data_cache.get("release_results", {})
                if release_results:
                    self.table.blockSignals(True)
                    try:
                        for col_idx, col_obj in enumerate(self.active_columns):
                            if isinstance(col_obj, ReleaseResultColumn) and col_obj.name in release_results:
                                loading.append_log(f"Restoring results for {col_obj.name}...")
                                result_list = release_results[col_obj.name]
                                
                                # Apply to table
                                for row, val in enumerate(result_list):
                                    if row >= self.table.rowCount(): break # Safety
                                    
                                    # Update visual state using on_change
                                    if val:
                                        col_obj.on_change(self.table, row, col_idx, val, self)
                    finally:
                        self.table.blockSignals(False)
                
            # Req 8: Run initialization logic for any new columns that haven't run yet
            self._run_column_initialization_logic()
            
            # Step 5: Handle Default Cyclicity Updates if requested
            if update_existing_cyclic:
                 self._apply_default_cyclicity_update()
        finally:
            loading.close()
            loading.deleteLater()
            QCoreApplication.processEvents()

    def _apply_default_cyclicity_update(self):
        """Helper to update existing 'Auto' cyclic ports to new default."""
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                for col_idx, col_obj in enumerate(self.active_columns):
                    if isinstance(col_obj, CyclicColumn):
                         item = self.table.item(row, col_idx)
                         # Only update if NOT user changed (meaning it is Auto)
                         if item and not UserInteractionLogic.is_item_user_changed(item):
                             # Re-trigger on_change to recalculate default
                             col_obj.on_change(self.table, row, col_idx, "", self)
        finally:
            self.table.blockSignals(False)

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

        self.table.blockSignals(True)
        try:
            arch_state = current_model.status # "Released", "In Work", "Retired"
            port_state_idx = self.get_column_index_by_type("PortStateColumn")
            for col_idx, col_obj in enumerate(self.active_columns):
                if isinstance(col_obj, ReleaseResultColumn):
                    # Check if this release column is baselined
                    col_name = col_obj.name
                    release_name = ""
                    if col_name.startswith("Release_") and col_name.endswith("_Result"):
                        release_name = col_name[len("Release_"):-len("_Result")]

                    is_baselined = False
                    if hasattr(self, 'release_manager') and self.release_manager:
                        is_baselined = any(r.is_baseline and not r.is_deleted and r.parent_release_name == release_name 
                                           for r in self.release_manager.releases)

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

                        if is_baselined:
                            new_val = "No Result"
                        else:
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
        finally:
            self.table.blockSignals(False)

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

    def populate_from_parser(self, parser, release_name=None, skip_release_create=False):
        """
        Initializes the matcher when a new ELF/JSON is successfully loaded.
        When skip_release_create=True the release was already created by the DB loader.
        """
        if not parser:
            logger.error("Received empty parser in ArchitectureTabController")
            return

        self.parser = parser
        db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
        elf_hash = getattr(parser, 'md5_hash', None) or getattr(parser, '_active_elf_hash', None)
        if db and db.is_open and elf_hash:
            self.matcher = SymbolMatcher(parser, db=db, elf_hash=elf_hash)
        else:
            self.matcher = SymbolMatcher(parser)

        # Build and save an initial basic CodeMap if one doesn't exist yet for this model
        active_model_id = getattr(self.model_manager, 'active_model_id', None)
        if db and db.is_open and active_model_id is not None and parser:
            try:
                if not db.get_model_code_map(active_model_id):
                    from Application_Logic.Logic_Code_Map import build_code_map
                    import json
                    code_map = build_code_map(parser, None, source_root="")
                    db.save_model_code_map(active_model_id, json.dumps(code_map))
            except Exception as e:
                logger.warning(f"Failed to build initial CodeMap on parser population: {e}")

        # Create the Release Node if name provided and not skipped
        if release_name and not skip_release_create:
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
                 self.release_manager.create_release(
                     release_name,
                     elf_path=str(parser.elf_path) if parser.elf_path else "",
                     elf_hash=parser.md5_hash,
                 )
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
                 
                 logger.warning("Release creation warning: %s", e)
                 # If it exists, find it and select it
                 for i, r in enumerate(self.release_manager.releases):
                     if r.name == release_name:
                         self.release_manager.set_active_release(i)
                         break

        # UI Feedback
        self.ui.statusbar.showMessage("Matcher ready. Enter Port Names to begin matching.")
        logger.debug("Matcher initialized with %d symbols.", len(self.matcher.search_pool))

    def refresh_fuzzy_matches(self, show_progress=False,
                              progress_label="Matching symbols, please wait..."):
        """
        Eagerly re-run the *active* fuzzy-match branch for every search column in
        every row, populating the adjacent (Match) column immediately against the
        currently loaded matcher (ELF).

        This is the same path that runs when a user types into a search cell
        (``on_change`` with ``lazy=False``), so the (Match) columns are filled with
        real fuzzy results instead of waiting for the user to open each lazy
        dropdown. Used on import and whenever a different ELF is loaded.

        Project loading deliberately keeps the lazy branch and is not routed here.
        """
        if not self.matcher:
            return

        search_cols = [
            (i, col) for i, col in enumerate(self.active_columns)
            if isinstance(col, (PortSearchColumn, FunctionSearchColumn, VariableSearchColumn))
        ]
        if not search_cols:
            return

        row_count = self.table.rowCount()

        from PyQt6.QtCore import QCoreApplication

        loading = None
        if show_progress and self.main_window and self.main_window.isVisible():
            from .Logic_Loading_Window import LoadingDialog
            loading = LoadingDialog(self.main_window)
            loading.ui.lbl_loading_text.setText(progress_label)
            # Non-modal on purpose: this runs synchronously on the UI thread, so an
            # app-modal session adds nothing and, shown via show()/close() instead
            # of exec(), can leave a dangling modal session on macOS that silently
            # disables the sidebar buttons until the app is restarted.
            loading.show()
            QCoreApplication.processEvents()

        self.table.blockSignals(True)
        try:
            for row in range(row_count):
                for col_idx, col_obj in search_cols:
                    text = self.get_cell_value(row, col_idx)
                    if text:
                        # lazy defaults to False -> eager match, populates (Match) column now
                        col_obj.on_change(self.table, row, col_idx, text, self)
                if loading is not None and (row % 25 == 0 or row == row_count - 1):
                    loading.append_log(f"Matched {row + 1}/{row_count} rows...")
                    QCoreApplication.processEvents()
        finally:
            self.table.blockSignals(False)
            self.hook_comboboxes()
            self.refresh_init_column_state()
            self.refresh_cyclic_column_state()
            if loading is not None:
                loading.close()
                loading.deleteLater()
                QCoreApplication.processEvents()

    def get_cell_value(self, row, col_idx):
        """Helper to get text value of a cell, checking widgets first."""
        widget = self.table.cellWidget(row, col_idx)
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        item = self.table.item(row, col_idx)
        return item.text() if item else ""

    def on_item_changed(self, item):
        """
        Unified handler for fuzzy matching, dynamic row addition, and cleanup.
        """
        if self.table.signalsBlocked():
            return

        row = item.row()
        col_idx = item.column()
        
        # Get old value (Feature 5)
        old_val = getattr(self, "_pre_edit_value", "")
        pre_row = getattr(self, "_pre_edit_row", -1)
        pre_col = getattr(self, "_pre_edit_col", -1)
        if pre_row != row or pre_col != col_idx:
            old_val = ""

        # Issue 2: Reset review status on any edit to INPUT columns (covers Static Text, Init, Cyclic, etc.)
        # Exclude output/status/metadata columns
        is_input_col = True
        if col_idx < len(self.active_columns):
            col_obj = self.active_columns[col_idx]
            if isinstance(col_obj, (ReviewColumn, PortStateColumn, LastResultColumn, ReleaseResultColumn, LinkColumn)):
                is_input_col = False
                
        if is_input_col:
            UserInteractionLogic.reset_review_status(self.table, row, self)
        
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
                    # Retrieve current text/widget value to preserve state, or let it default
                    curr_text = self.get_cell_value(row, i)
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
                    self._mark_row_dirty(new_row)
                    self._full_flush_needed = True  # Row insertion shifts indices
        finally:
            self.table.blockSignals(False)
            # Only the edited row (and a possibly-appended last row) can have new
            # widgets, so rehook just those — not the whole table on every
            # keystroke. Bulk paths (load/import/init) still call hook_comboboxes().
            self._hook_comboboxes_in_row(row)
            last_row = self.table.rowCount() - 1
            if last_row != row:
                self._hook_comboboxes_in_row(last_row)

        # Handle cell change history & save after Strategy has finished and signals are unblocked (Feature 5)
        new_val = item.text()
        if old_val != new_val:
            col_name = self.active_columns[col_idx].name if col_idx < len(self.active_columns) else f"Column {col_idx}"
            self._mark_row_dirty(row)
            self.handle_table_cell_change(row, col_name, old_val, new_val)
            # Update pre-edit value so subsequent changes work
            self._pre_edit_row = row
            self._pre_edit_col = col_idx
            self._pre_edit_value = new_val

    def handle_generate(self):
        if hasattr(self.main_window, 'test_case_controller'):
            QtCore.QTimer.singleShot(0, self.main_window.test_case_controller.show_generation_menu)
        else:
            logger.warning("Generation triggered but TestCaseDesignController is not initialized.")


    def on_model_selection_changed(self, current, previous):
        if getattr(self, 'is_loading', False):
            return
        if not current.isValid():
            return
            
        real_index = self.list_model.get_real_index(current.row())
        if real_index == -1:
            return
        if real_index == self.model_manager.active_model_index:
            return
            
        # 1. Save current table data to the OLD active model
        self.flush_current_data_to_model()
        self._dirty_rows.clear()
        self._row_snapshots.clear()
        self._full_flush_needed = False

        # 2. Set new active model
        self.model_manager.set_active_model(real_index)
        
        # 3. Load data
        self.load_active_model_to_table()

    # Removed duplicate flush_current_data_to_model (was lines 1021-1038)


    def show_sidebar_context_menu(self, pos):
        # Open the Manager Window
        if not getattr(self.main_window, 'edit_mode', True):
            return
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
            self.load_active_model_to_table()
            # Reload ELF from the active release's cached database so symbol search stays current
            active_release = self.release_manager.get_active_release()
            if active_release and active_release.data_cache:
                elf_data = active_release.data_cache.get("database", {})
                if elf_data:
                    ProjectSaver._populate_parser(self.main_window, elf_data)

    def load_active_model_to_table(self):
        """Loads the currently active ArchitectureModel into the table"""
        current_model = self.model_manager.get_active_model()
        if not current_model:
            # Clear table if no models?
            # Or create default? Manager usually ensures at least one.
            return

        self.main_window.setWindowTitle(f"Architecture Testing Tool - {current_model.name}")
        
        from PyQt6.QtCore import QCoreApplication

        # Lazy-load model data from DB if not yet in cache
        if current_model.data_cache is None:
            self.model_manager._load_model_data(current_model)

        # Get rows from the model's cache
        rows_data = []
        if current_model.data_cache:
            rows_data = current_model.data_cache.get("rows", [])

        # FIX: Restore Project/Model Configuration (Phantom Columns Fix)
        # If the model has a saved configuration, we must restore it to the controller.
        # Otherwise, the controller keeps the previous model's config, leading to schema drift.
        model_config = current_model.data_cache.get("config", []) if current_model.data_cache else []
        if model_config:
            # Only update if different (optimization)
            # But deep comparison is safe enough
            if self.active_config != model_config:
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
                self.table.blockSignals(True)
                try:
                    for col_idx, col_obj in enumerate(self.active_columns):
                        if isinstance(col_obj, ReleaseResultColumn) and col_obj.name in release_results:
                            result_list = release_results[col_obj.name]
                            
                            # Apply to table
                            for row, val in enumerate(result_list):
                                if row >= self.table.rowCount(): break # Safety
                                
                                # Update visual state using on_change (handles widget creation/coloring/item text)
                                # We pass the value even if empty to ensure formatting
                                if val:
                                    col_obj.on_change(self.table, row, col_idx, val, self)
                finally:
                    self.table.blockSignals(False)
            
            # If a linked release column is defined, force update the Last Result column values
            if current_model.data_cache and "linked_release_column" in current_model.data_cache:
                # Find the LastResultColumn
                last_res_col_obj = None
                for col_obj in self.active_columns:
                    if isinstance(col_obj, LastResultColumn):
                        last_res_col_obj = col_obj
                        break
                if last_res_col_obj:
                    self.table.blockSignals(True)
                    try:
                        for row in range(self.table.rowCount()):
                            last_res_col_obj._update_last_result(self.table, row, self)
                    finally:
                        self.table.blockSignals(False)

            # Run Logic (skips if initialized OR if data exists)
            self._run_column_initialization_logic()
            
            # Restore filters
            self.apply_port_state_filters()

    def set_project_path(self, path, flush=True):
        """Called by ProjectSaver or Main when project path is established/changed."""
        # Update both managers
        self.model_manager.set_project_path(path)
        self.release_manager.set_project_path(path)
        
        # Flush current to the new path immediately
        if flush:
            self.flush_current_data_to_model()

    def reset_controller(self):
        """
        Resets the controller to a clean state, discarding any previous project's models, releases, and settings.
        """
        self._db = None
        self.parser = None
        self.matcher = None

        # Reset Managers
        self.model_manager._db = None
        self.model_manager.project_path = None
        self.model_manager.models = []
        self.model_manager.active_model_index = 0
        self.model_manager._create_default_model_in_memory()
        
        self.release_manager._db = None
        self.release_manager.project_path = None
        self.release_manager.releases = []
        self.release_manager.active_release_index = -1
        
        # Reset settings and metadata
        self.current_default_cyclicity = "10"
        self.show_retired = True
        self.show_deleted = False
        self.column_metadata = {}
        self.permanently_locked_columns = set()
        self._dirty_rows.clear()
        self._full_flush_needed = False
        self._autosave_timer.stop()
        
        # Reset columns to default configuration
        self.active_config = [
            ("TC. ID", "Static Text", True),
            ("Input Port", "Port Search", True), ("Input Port (Match)", "Static Text", True), ("Input Port (Init)", "InitColumn", None), ("Input Port (Cyclic)", "CyclicColumn", None),
            ("Mapped Func", "Function Search", True), ("Mapped Func (Match)", "Static Text", True), ("Mapped Func (Init)", "InitColumn", None), ("Mapped Func (Cyclic)", "CyclicColumn", None),
            ("Mapped Parameter", "Variable Search", True), ("Mapped Parameter (Match)", "Static Text", True),
            ("Review Status", "Review Status", True),
            ("Port State", "PortStateColumn", True),
        ]
        
        # Rebuild objects and update table style
        self._rebuild_column_objects()
        self._setup_table_style()
        
        # Refresh list model
        self.list_model.refresh()
        self.load_active_model_to_table()

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
            self.active_config.append((last_res_name, "Last Result", True))

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

        # Mark dirty so the new column is persisted on the next autosave tick
        if getattr(self.main_window, 'current_project_file', None):
            self._autosave_timer.start()

    def refresh_all_column_locking(self):
        """
        Re-evaluates and applies dynamic locking/editability for all cells in the table,
        based on active mode, baseline status, and column-specific rules.
        """
        self.table.blockSignals(True)
        try:
            is_baseline_view = hasattr(self, 'btn_exit_baseline') and not self.btn_exit_baseline.isHidden()
            for row in range(self.table.rowCount()):
                for col_idx, col_obj in enumerate(self.active_columns):
                    widget = self.table.cellWidget(row, col_idx)
                    item = self.table.item(row, col_idx)
                    text = self.get_cell_value(row, col_idx)
                    
                    if isinstance(col_obj, ReleaseResultColumn):
                        col_name = col_obj.name
                        release_name = ""
                        if col_name.startswith("Release_") and col_name.endswith("_Result"):
                            release_name = col_name[len("Release_"):-len("_Result")]

                        is_active = False
                        is_baselined = False
                        if hasattr(self, 'release_manager') and self.release_manager:
                            active_rel = self.release_manager.get_active_release()
                            if active_rel:
                                is_active = (active_rel.name == release_name)
                            is_baselined = any(r.is_baseline and not r.is_deleted and r.parent_release_name == release_name 
                                               for r in self.release_manager.releases)

                        should_lock = (not is_active) or is_baselined or is_baseline_view

                        if widget:
                            widget.setEnabled(not should_lock)
                        
                        if item:
                            if should_lock:
                                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                            else:
                                if text != "No Result":
                                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                                    
                    elif isinstance(col_obj, (PortStateColumn, ReviewColumn, LinkColumn)):
                        if is_baseline_view:
                            if widget:
                                widget.setEnabled(False)
                            if item:
                                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                        else:
                            # Re-enable if in regular edit mode
                            edit_mode = getattr(self.main_window, 'edit_mode', True)
                            if widget:
                                widget.setEnabled(edit_mode)
                            if item:
                                if edit_mode:
                                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                                else:
                                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        finally:
            self.table.blockSignals(False)


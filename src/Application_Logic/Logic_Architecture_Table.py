from PyQt6 import QtWidgets, QtCore, QtGui
from .Logic_Symbol_Matcher import SymbolMatcher
from .Logic_Column_Customizer import ColumnCustomizer
from .Logic_Column_Types import TableColumn, PortSearchColumn, FunctionSearchColumn, VariableSearchColumn, ReviewColumn, InitColumn


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
        }

        # Current configuration: (Column Name) -> (Logic Instance)
        self.active_columns = []
        self.active_config = [
            ("TC. ID", "Static Text"),
            ("Input Port", "Port Search"),
            ("Mapped Func", "Function Search"),
            ("Mapped Parameter", "Variable Search"),
            ("Review Status", "Review Status"),
            ("Cyclic", "Static Text")
        ]
        self.active_columns = []
        self._rebuild_column_objects()
        self._setup_table_style()
        self._connect_signals()

    def _rebuild_column_objects(self):
        """
        Converts the config tuples (active_config) into actual logic instances
        Search types automatically generate a paired 'Result' column.
        The Init column is injected automatically if search function exists
        """
        config = getattr(self, 'active_config', [])
        self.active_columns = []
        needs_init = False

        for name, logic_key in config:
            logic_cls = self.available_logics.get(logic_key, TableColumn)
            self.active_columns.append(logic_cls(name))

            if "Search" in logic_key:
                result_col = TableColumn(f"{name} (Match)", width=200)
                self.active_columns.append(result_col)
                # If we have Port or Function search, we might need the Init toggle
                if "Port" in logic_key or "Function" in logic_key:
                    needs_init = True

                # Internal injection: Add Init column if needed, but it's not in the user's config
            if needs_init:
                self.active_columns.append(InitColumn("Init", width=60))

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

        # 3. Row handling
        if self.table.rowCount() == 0:
            self.table.insertRow(0)
            self._initialize_row_widgets(0)

    def refresh_init_column_state(self):
        """
        Scans all search results and toggles visibility of the Init column.
        """
        init_idx = self.get_column_index_by_type("Init")
        if init_idx == -1: return

        any_init_found = False
        self.table.blockSignals(True)

        for row in range(self.table.rowCount()):
            row_has_init = False

            # Check all columns in this row for search widgets
            for col in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, col)
                if isinstance(widget, QtWidgets.QComboBox):
                    # Use currentText() to catch both 'DSU_init (90%)' and cleaned 'DSU_init'
                    if "init" in widget.currentText().lower():
                        row_has_init = True
                        any_init_found = True
                        break

            # Update cell value
            val = "1" if row_has_init else "0"
            self.table.setItem(row, init_idx, QtWidgets.QTableWidgetItem(val))
            # Center the text for better visibility
            self.table.item(row, init_idx).setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.table.blockSignals(False)
        # Toggle global visibility of the column
        self.table.setColumnHidden(init_idx, not any_init_found)



    def _initialize_row_widgets(self, row):
        """Ensures widgets like the Review dropdown are created for a new row."""
        for col_idx, col_obj in enumerate(self.active_columns):
            col_obj.on_change(self.table, row, col_idx, "", self)

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
        logic_options = list(self.available_logics.keys())

        dialog = ColumnCustomizer(self.active_config, logic_options, self.main_window)
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
                item = self.table.item(row, col_idx)
                row_data[header] = item.text() if item else ""
            old_data.append(row_data)

        # Update the configuration and objects
        self.active_config = column_names
        self._rebuild_column_objects()

        # Reconfigure the UI
        self.table.blockSignals(True)
        self._setup_table_style()

        # Map old data back to new column positions by Header Name
        for row_idx, row_dict in enumerate(old_data):
            for col_idx, col_obj in enumerate(self.active_columns):
                val = row_dict.get(col_obj.name, "")
                if val:
                    self.table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(val))

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
        col_idx = item.column()
        text = item.text().strip()

        self.table.blockSignals(True)
        try:
            # CHANGE: Instead of just calling one strategy,
            # we notify ALL columns in this row that something changed.
            for i, strategy in enumerate(self.active_columns):
                # Pass the text if it's the edited column, otherwise empty string
                # The strategies (Review/Init) will check table.item() themselves.
                val = text if i == col_idx else ""
                strategy.on_change(self.table, row, i, val, self)

            # Auto-add new row logic
            if row == self.table.rowCount() - 1 and text != "":
                new_row = self.table.rowCount()
                self.table.insertRow(new_row)
                self._initialize_row_widgets(new_row)
        finally:
            self.table.blockSignals(False)

    def handle_generate(self):
        print("Generation triggered...")
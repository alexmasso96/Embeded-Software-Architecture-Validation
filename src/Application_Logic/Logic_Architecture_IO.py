"""
Architecture Table — I/O Mixin
Handles serialisation (get_project_data, flush_current_data_to_model)
and deserialisation (_load_row_data, load_project_data, _restore_row_logic).
"""
import json

from PyQt6 import QtWidgets

from .Logic_Column_Types import (
    ReleaseResultColumn, ReviewColumn,
    PortSearchColumn, FunctionSearchColumn, VariableSearchColumn,
    PortStateColumn, LastResultColumn, LinkColumn,
)
from .Logic_User_Interaction import UserInteractionLogic


class ArchitectureIOMixin:

    # ------------------------------------------------------------------
    # Collect / Serialise
    # ------------------------------------------------------------------

    def get_project_data(self):
        """Collects all data required to save the project."""
        reverse_logics = {v: k for k, v in self.available_logics.items()}
        updated_config = []
        for i, col_obj in enumerate(self.active_columns):
            width = self.table.columnWidth(i)
            if i < len(self.active_config):
                old_tuple = self.active_config[i]
                visible = old_tuple[2] if len(old_tuple) > 2 else True
                updated_config.append((old_tuple[0], old_tuple[1], visible, width))
            else:
                logic_key = reverse_logics.get(type(col_obj), "Static Text")
                updated_config.append((col_obj.name, logic_key, col_obj.user_visible, width))
        self.active_config = updated_config

        project_data = {
            "config": self.active_config,
            "settings": {
                "default_cyclicity": self.current_default_cyclicity,
                "show_retired": self.show_retired,
                "show_deleted": self.show_deleted,
            },
            "rows": [],
        }

        for row in range(self.table.rowCount()):
            row_data = {}
            for col_idx, col_obj in enumerate(self.active_columns):
                cell_info = {}
                item = self.table.item(row, col_idx)
                if item:
                    cell_info["text"] = item.text()
                    cell_info["user_changed"] = UserInteractionLogic.is_item_user_changed(item)
                    cell_info["is_purple"] = UserInteractionLogic.is_purple(item)
                    cell_info["last_func"] = UserInteractionLogic.get_last_function(item)
                else:
                    cell_info["text"] = ""

                widget = self.table.cellWidget(row, col_idx)
                if isinstance(widget, QtWidgets.QComboBox):
                    cell_info["widget_text"] = widget.currentText()
                    cell_info["widget_style"] = widget.styleSheet()

                row_data[col_obj.name] = cell_info
            project_data["rows"].append(row_data)

        return project_data

    def flush_current_data_to_model(self):
        """Saves current table rows into the active ArchitectureModel's cache and file."""
        current_model = self.model_manager.get_active_model()
        if not current_model:
            return

        full_data = self.get_project_data()
        full_data["column_metadata"] = self.column_metadata

        existing_results = (
            current_model.data_cache.get("release_results", {})
            if current_model.data_cache
            else {}
        )
        release_results = {}

        for col_idx, col_obj in enumerate(self.active_columns):
            if isinstance(col_obj, ReleaseResultColumn):
                col_data = []
                existing_col_data = existing_results.get(col_obj.name, [])

                for row in range(self.table.rowCount()):
                    val = ""
                    widget = self.table.cellWidget(row, col_idx)
                    item = self.table.item(row, col_idx)

                    if widget and isinstance(widget, QtWidgets.QComboBox):
                        val = widget.currentText()
                    elif item:
                        val = item.text()

                    if val in ["No Result", "Not Run", "Block"] and row < len(existing_col_data):
                        prev_val = existing_col_data[row]
                        if prev_val in ["Passed", "Failed", "Warning"]:
                            print(f"Preserving '{prev_val}' over '{val}' for {col_obj.name} Row {row}")
                            val = prev_val

                    col_data.append(val)
                release_results[col_obj.name] = col_data

        full_data["release_results"] = release_results

        if "config" in full_data:
            del full_data["config"]
        if "settings" in full_data:
            del full_data["settings"]

        if current_model.data_cache and "linked_release_column" in current_model.data_cache:
            full_data["linked_release_column"] = current_model.data_cache["linked_release_column"]

        current_model.data_cache = full_data

        print(
            f"DEBUG: Flushed data for '{current_model.name}' "
            f"(File: {current_model.file_path}). Rows: {len(full_data.get('rows', []))}"
        )

        if current_model.file_path:
            try:
                with open(current_model.file_path, 'w') as f:
                    json.dump(full_data, f, indent=4)
                print(f"DEBUG: Successfully wrote file {current_model.file_path}")
            except Exception as e:
                print(f"Auto-save model failed: {e}")

    # ------------------------------------------------------------------
    # Restore / Deserialise
    # ------------------------------------------------------------------

    def load_project_data(self, data):
        """Restores project state from a data dict (config + settings + rows)."""
        settings = data.get("settings", {})
        config = data.get("config", [])

        current_config_tuples = [tuple(x) for x in self.active_config]
        new_config_tuples = [tuple(c) for c in config]
        rebuild_needed = (current_config_tuples != new_config_tuples) or not self.active_columns

        if rebuild_needed:
            self.current_default_cyclicity = settings.get("default_cyclicity", "10")
            self.show_retired = settings.get("show_retired", True)
            self.show_deleted = settings.get("show_deleted", False)
            self.active_config = new_config_tuples
            self._rebuild_column_objects()
            self.table.clear()
            self.table.setRowCount(0)
            self._setup_table_style()
        else:
            self.show_retired = settings.get("show_retired", True)
            self.show_deleted = settings.get("show_deleted", False)

        rows = data.get("rows", [])
        self._load_row_data(rows)

    def _load_row_data(self, rows):
        """Efficiently loads row data into the existing table schema."""
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(rows))

            for row_idx, row_data in enumerate(rows):
                # Pass 1: Restore item text and metadata
                for col_idx, col_obj in enumerate(self.active_columns):
                    cell_info = row_data.get(col_obj.name, {})
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

                # Pass 2: Create widgets (lazy — skip expensive search logic)
                self._initialize_row_widgets(row_idx, lazy=True, row_data=row_data)

                # Pass 3: Restore widget selection and style
                for col_idx, col_obj in enumerate(self.active_columns):
                    cell_info = row_data.get(col_obj.name, {})
                    widget_text = cell_info.get("widget_text")
                    if widget_text:
                        widget = self.table.cellWidget(row_idx, col_idx)
                        if isinstance(widget, QtWidgets.QComboBox):
                            if isinstance(col_obj, ReviewColumn) and widget_text == "Broken Link":
                                if widget.findText("Broken Link") == -1:
                                    widget.addItem("Broken Link")
                            widget.blockSignals(True)
                            widget.setCurrentText(widget_text)
                            widget_style = cell_info.get("widget_style")
                            if widget_style:
                                widget.setStyleSheet(widget_style)
                            widget.blockSignals(False)

                # Pass 4: Re-trigger logic (colors, side-effects)
                self._restore_row_logic(row_idx)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        self.refresh_init_column_state()
        self.refresh_cyclic_column_state()
        self.apply_port_state_filters()
        self.hook_comboboxes()

    def _restore_row_logic(self, row):
        """Re-triggers widget logic for one row after a blocked load."""
        for col_idx, col_obj in enumerate(self.active_columns):
            widget = self.table.cellWidget(row, col_idx)
            if not widget:
                continue

            if isinstance(col_obj, ReviewColumn):
                if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_status_change(self.table, row, col_idx, widget.currentText())

            elif isinstance(col_obj, PortStateColumn):
                if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_state_change(self.table, row, col_idx, widget.currentText(), self)

            elif isinstance(col_obj, (PortSearchColumn, FunctionSearchColumn, VariableSearchColumn)):
                if isinstance(widget, QtWidgets.QComboBox):
                    import re
                    text = widget.currentText()
                    match = re.search(r'\((\d+)%\)$', text)
                    if match:
                        score = int(match.group(1))
                        color = "#2e8b57" if score >= 80 else "#b8860b" if score >= 60 else "#8b0000"
                        status = UserInteractionLogic.get_review_status(self.table, row, self)
                        if status == "Reviewed":
                            color = "#2e8b57"
                        elif status == "Broken Link":
                            color = "#483d8b"
                        widget.setStyleSheet(f"color: {color}; font-weight: bold;")

            elif isinstance(col_obj, (ReleaseResultColumn, LastResultColumn)):
                if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_state_change(self.table, row, col_idx, widget.currentText(), self)

            elif isinstance(col_obj, LinkColumn):
                if isinstance(widget, QtWidgets.QComboBox):
                    col_obj._handle_change(self.table, row, col_idx, widget.currentText(), self)

        self.hook_comboboxes()

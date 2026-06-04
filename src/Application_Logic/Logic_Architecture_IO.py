"""
Architecture Table — I/O Mixin
Handles serialisation (get_project_data, flush_current_data_to_model)
and deserialisation (_load_row_data, load_project_data, _restore_row_logic).
"""
import os
import time
import logging

from PyQt6 import QtWidgets

_PERF_LOG = os.environ.get("ARCH_PERF_LOG", "0") == "1"
_perf_logger = logging.getLogger("arch.perf")

from .Logic_Column_Types import (
    ReleaseResultColumn, ReviewColumn,
    PortSearchColumn, FunctionSearchColumn, VariableSearchColumn,
    PortStateColumn, LastResultColumn, LinkColumn, _match_style,
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
                # Hidden columns report width 0 — keep their stored width so they
                # don't reappear at zero width when later re-shown.
                if width <= 0:
                    width = old_tuple[3] if len(old_tuple) > 3 and old_tuple[3] else col_obj.width
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
        """Saves current table rows into the active ArchitectureModel's cache and DB."""
        _t0 = time.perf_counter() if _PERF_LOG else 0
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

        # Persist to DB
        db = getattr(self, '_db', None) or getattr(self.main_window, 'project_db', None)
        if db and db.is_open and current_model.id is not None:
            db.save_model_rows(current_model.id, full_data.get("rows", []))
            # Persist model-specific metadata (column_metadata, release_results,
            # linked_release_column) to the model_metadata table so it survives
            # across sessions.  These keys are merged back into data_cache on load
            # by _load_model_data().
            meta_to_save = {}
            col_meta = full_data.get("column_metadata", {})
            if col_meta:
                meta_to_save["column_metadata"] = col_meta
            release_results = full_data.get("release_results", {})
            if release_results:
                meta_to_save["release_results"] = release_results
            lrc = full_data.get("linked_release_column")
            if lrc is not None:
                meta_to_save["linked_release_column"] = lrc
            db.save_model_metadata(current_model.id, meta_to_save)
            db.commit()
            if _PERF_LOG:
                ms = (time.perf_counter() - _t0) * 1000
                _perf_logger.info("[PERF] flush_current_data_to_model  model=%s rows=%d  %.1f ms",
                                  current_model.name, len(full_data.get("rows", [])), ms)

    # ------------------------------------------------------------------
    # Restore / Deserialise
    # ------------------------------------------------------------------

    def load_project_data(self, data):
        """Restores project state from a data dict (config + settings + rows).

        A Software Release data dict carries only ``rows`` (plus results/metadata)
        and intentionally has no ``config`` or ``settings`` — releases share the
        architecture model's current column schema and only overlay their own row
        data.  In that case we must keep the existing columns and filters and just
        reload the rows; rebuilding from an empty config would wipe every column,
        leaving only the row-number gutter (the ELF-reload "columns disappeared"
        bug).  Rebuild only when a real config is supplied, or when the table has
        no columns yet.
        """
        config = data.get("config", [])
        current_config_tuples = [tuple(x) for x in self.active_config]
        new_config_tuples = [tuple(c) for c in config]
        rebuild_needed = (
            (bool(new_config_tuples) and current_config_tuples != new_config_tuples)
            or not self.active_columns
        )

        if "settings" in data:
            settings = data["settings"]
            self.current_default_cyclicity = settings.get(
                "default_cyclicity", self.current_default_cyclicity)
            self.show_retired = settings.get("show_retired", self.show_retired)
            self.show_deleted = settings.get("show_deleted", self.show_deleted)

        if rebuild_needed:
            self.active_config = new_config_tuples
            self._rebuild_column_objects()
            self.table.clear()
            self.table.setRowCount(0)
            self._setup_table_style()

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

                self._initialize_row_widgets(row_idx, lazy=True, row_data=row_data)

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
                        color = _match_style(score)
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

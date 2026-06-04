"""
Architecture Table — Excel Import Mixin
Handles import_architecture_excel and the word-similarity helper it relies on.
Supports both legacy sheet-per-model Excel format and Rhapsody path-based exports.
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

from PyQt6 import QtWidgets
from rapidfuzz import fuzz

from .Logic_Column_Types import (
    PortSearchColumn, FunctionSearchColumn, VariableSearchColumn,
    LinkColumn, PortStateColumn, _match_style,
)
from .Logic_Project_Saving import ProjectSaver
from UI.Dialog_Architecture_Import import (
    ImportModeDialog,
    ManualImportDialog,
    FuzzyMatchPromptDialog,
    ImportConfirmationDialog,
)


class ArchitectureImportMixin:

    def _eager_match_imported_models(self, models):
        """Populate the (Match) columns for every model that received imported
        rows, matching against the active matcher.

        A single import distributes rows across several models (one per sheet),
        and newly-created models are *not* made active by ``create_model``.
        Matching only the active model would leave every other imported model
        showing the lazy placeholder (raw search text) until the user manually
        opens each dropdown.

        Rather than activate each touched model in turn and route the match
        through the live table (which made the UI visibly jump from model to
        model), we compute the best fuzzy match directly in each model's cached
        row data — no active-model switching, no per-model table reload. A single
        loading overlay covers the whole pass, and only the already-active model
        is reloaded at the end so its freshly matched rows are shown. The matches
        live in each model's ``data_cache`` and are persisted to the DB by the
        ``save_project`` call that follows every import.
        """
        # Dedupe while preserving order; drop Nones.
        seen = set()
        unique_models = []
        for m in models:
            if m is not None and id(m) not in seen:
                seen.add(id(m))
                unique_models.append(m)

        loading = None
        if (self.matcher and unique_models
                and self.main_window and self.main_window.isVisible()):
            from PyQt6.QtCore import QCoreApplication
            from .Logic_Loading_Window import LoadingDialog
            loading = LoadingDialog(self.main_window)
            loading.ui.lbl_loading_text.setText(
                "Importing — matching symbols, please wait...")
            # Deliberately NON-modal: matching runs synchronously on the UI thread
            # (the loop already blocks interaction), so an app-modal session here
            # buys nothing and, when shown via show()/close() rather than exec(),
            # can leave a dangling modal session on macOS that silently kills the
            # sidebar buttons until the app is restarted.
            loading.show()
            QCoreApplication.processEvents()

        try:
            if self.matcher:
                from PyQt6.QtCore import QCoreApplication
                for i, model in enumerate(unique_models, 1):
                    self._match_model_data_inplace(model)
                    if loading is not None:
                        loading.append_log(
                            f"Matched {i}/{len(unique_models)}: {model.name}")
                        QCoreApplication.processEvents()
        finally:
            if loading is not None:
                from PyQt6.QtCore import QCoreApplication
                loading.close()
                loading.deleteLater()
                QCoreApplication.processEvents()

        # Refresh the view for whichever model is currently active so its newly
        # imported, freshly matched rows are shown. The active model's rows were
        # flushed to its data_cache before import, so one reload is enough — we
        # never switch the active model, so the table no longer jumps.
        self.load_active_model_to_table()

    def _match_model_data_inplace(self, model):
        """Compute the best fuzzy match for every search column in a model's
        cached rows and write it into the adjacent (Match) column cell
        (``widget_text`` + ``widget_style``), without touching the table.

        Mirrors exactly what the table path produced via ``_update_dropdown`` +
        ``flush_current_data_to_model``: the (Match) cell stores ``"Name (NN%)"``
        as ``widget_text`` and a score-coloured stylesheet. The match for a
        search column lives in the *next* column — all imported models share the
        active schema, since their rows are built from ``self.active_columns`` at
        import time, so we read that schema to locate each (Match) column.
        """
        if not self.matcher or not model.data_cache:
            return
        rows = model.data_cache.get("rows")
        if not rows:
            return

        specs = []
        for i, col_obj in enumerate(self.active_columns):
            if isinstance(col_obj, (PortSearchColumn, FunctionSearchColumn,
                                    VariableSearchColumn)):
                if i + 1 < len(self.active_columns):
                    specs.append(
                        (col_obj.name, self.active_columns[i + 1].name, type(col_obj)))
        if not specs:
            return

        for row_dict in rows:
            for search_name, match_name, col_type in specs:
                text = row_dict.get(search_name, {}).get("text", "").strip()
                if not text:
                    continue
                if col_type is FunctionSearchColumn:
                    matches = self.matcher.find_top_function_matches(text, limit=10)
                elif col_type is VariableSearchColumn:
                    matches = self.matcher.find_top_variable_matches(text, limit=10)
                else:
                    matches = self.matcher.find_top_matches(text, limit=10)
                if not matches:
                    continue
                best_name, best_score = matches[0]
                cell = row_dict.setdefault(match_name, {"text": ""})
                cell["widget_text"] = f"{best_name} ({best_score}%)"
                cell["widget_style"] = (
                    f"background-color: {_match_style(best_score)}; color: white;")

    def calculate_word_similarity(self, name1: str, name2: str) -> float:
        """
        Word-based similarity: splits camelCase/underscores/dashes and matches
        word-by-word.  Words ≤ 2 chars need an exact match; longer words use
        rapidfuzz ratio with a threshold of 85.
        """
        def split_into_words(s):
            s_camel = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
            s_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', s_camel)
            return [w.lower() for w in s_clean.split() if w.strip()]

        words1 = split_into_words(name1)
        words2 = split_into_words(name2)

        if not words1 or not words2:
            return 0.0

        matched_count = 0
        used_indices: set = set()

        for w1 in words1:
            best_idx = -1
            best_score = 0
            for idx, w2 in enumerate(words2):
                if idx in used_indices:
                    continue
                if w1 == w2:
                    match_score = 100
                elif len(w1) > 2 and len(w2) > 2:
                    score = fuzz.ratio(w1, w2)
                    match_score = score if score >= 85 else 0
                else:
                    match_score = 0
                if match_score > best_score:
                    best_score = match_score
                    best_idx = idx
            if best_idx != -1:
                matched_count += 1
                used_indices.add(best_idx)

        return (2.0 * matched_count / (len(words1) + len(words2))) * 100.0

    def import_architecture_excel(self):
        """
        Imports software architecture ports from an Excel or CSV file.
        Auto-detects Rhapsody path-based exports and routes to a dedicated flow;
        otherwise runs the legacy sheet-per-model dialog state-machine.
        """
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Import Excel / CSV File", "",
            "Excel / CSV Files (*.xlsx *.xls *.csv)"
        )
        if not file_path:
            return

        self.flush_current_data_to_model()

        # -- Rhapsody path-based export detection --
        from Application_Logic.Logic_Rhapsody_Import import detect_rhapsody_format
        is_rhapsody, path_col = detect_rhapsody_format(file_path)
        if is_rhapsody:
            self._import_rhapsody(file_path, path_col)
            return

        # -- Legacy sheet-per-model Excel flow (unchanged) --
        if file_path.lower().endswith('.csv'):
            QtWidgets.QMessageBox.warning(
                self.main_window, "Unsupported Format",
                "CSV files are only supported for Rhapsody path-based exports.\n"
                "The selected file does not appear to be in that format."
            )
            return

        try:
            import pandas as pd
            xls = pd.ExcelFile(file_path)
            sheet_names = xls.sheet_names
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Import Error",
                f"Failed to load sheet names from Excel file:\n{str(e)}",
            )
            return

        if not sheet_names:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Import Warning",
                "No sheets found in the selected Excel file."
            )
            return

        # --- Dialog state-machine ---
        existing_models = [m.name for m in self.model_manager.models]
        mappings: dict = {}
        current_state = "MODE"

        while True:
            if current_state == "MODE":
                mode_dialog = ImportModeDialog(file_path, sheet_names, parent=self.main_window)
                if not mode_dialog.exec():
                    return

                mode = mode_dialog.selected_mode
                if mode == "automated":
                    mappings = {}
                    for sheet in sheet_names:
                        if sheet in existing_models:
                            mappings[sheet] = sheet
                        else:
                            candidates = [
                                (model_name, self.calculate_word_similarity(sheet, model_name))
                                for model_name in existing_models
                                if self.calculate_word_similarity(sheet, model_name) >= 50.0
                            ]
                            candidates.sort(key=lambda x: x[1], reverse=True)

                            if candidates:
                                fuzzy_dialog = FuzzyMatchPromptDialog(
                                    sheet, candidates, parent=self.main_window
                                )
                                mappings[sheet] = (
                                    fuzzy_dialog.selected_model
                                    if fuzzy_dialog.exec()
                                    else "<Create New Model>"
                                )
                            else:
                                mappings[sheet] = "<Create New Model>"
                    current_state = "CONFIRM"

                elif mode == "manual":
                    current_state = "MANUAL"

            elif current_state == "MANUAL":
                manual_dialog = ManualImportDialog(
                    sheet_names, existing_models, parent=self.main_window
                )
                if not manual_dialog.exec():
                    current_state = "MODE"
                    continue

                mappings = {
                    sheet: target_model
                    for sheet, (import_bool, target_model) in manual_dialog.mappings.items()
                    if import_bool
                }
                current_state = "CONFIRM"

            elif current_state == "CONFIRM":
                confirm_dialog = ImportConfirmationDialog(mappings, parent=self.main_window)
                if not confirm_dialog.exec():
                    return

                action = confirm_dialog.selected_action
                if action == "confirm":
                    break
                elif action == "advanced":
                    current_state = "MANUAL"
                else:
                    return

        # --- Ensure Link column exists ---
        has_link_col = any(col_data[1] == "Link" for col_data in self.active_config)
        if not has_link_col:
            self.active_config.append(("Link", "Link", True))
            self._rebuild_column_objects()
            self._setup_table_style()

        total_imported_ports = 0
        touched_models = []
        pattern = re.compile(
            r"^(.*?)\s*-\s*Port\s+(with|without)\s+TestCase\b", re.IGNORECASE
        )

        import pandas as pd  # already imported above, but guard for clarity

        for sheet_name, target_model_name in mappings.items():
            # Resolve target model
            if target_model_name == "<Create New Model>":
                unique_name = sheet_name
                existing_names = [m.name for m in self.model_manager.models]
                counter = 1
                while unique_name in existing_names:
                    unique_name = f"{sheet_name}_{counter}"
                    counter += 1
                model = self.model_manager.create_model(unique_name, "In Work")
                if not model.data_cache:
                    model.data_cache = {"rows": [], "config": self.active_config}
            else:
                model = next(
                    (m for m in self.model_manager.models if m.name == target_model_name), None
                )
                if not model:
                    continue
                if model == self.model_manager.get_active_model():
                    self.flush_current_data_to_model()
                if not model.data_cache:
                    model.data_cache = {"rows": [], "config": self.active_config}

            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            except Exception as e:
                logger.error("Error reading sheet %s: %s", sheet_name, e)
                continue

            # Build dedup set from existing rows
            existing_ports: set = set()
            for row_dict in model.data_cache.get("rows", []):
                for col_obj in self.active_columns:
                    if isinstance(col_obj, PortSearchColumn):
                        port_val = row_dict.get(col_obj.name, {}).get("text", "").strip()
                        if port_val:
                            existing_ports.add(port_val.lower())

            new_rows_count = 0

            for _, row in df.iterrows():
                val = str(row[0]).strip() if not pd.isna(row[0]) else ""
                if not val:
                    continue

                match = pattern.match(val)
                if match:
                    port_name = match.group(1).strip()
                    link_status = "Yes" if match.group(2).lower() == "with" else "No"
                else:
                    port_name = val
                    link_status = "No"

                if port_name.lower() in existing_ports:
                    # Update link status on the existing row
                    port_col_name = next(
                        (c.name for c in self.active_columns if isinstance(c, PortSearchColumn)),
                        None,
                    )
                    link_col_name = next(
                        (c.name for c in self.active_columns if isinstance(c, LinkColumn)),
                        None,
                    )
                    if port_col_name:
                        for row_dict in model.data_cache["rows"]:
                            if row_dict.get(port_col_name, {}).get("text", "").strip().lower() == port_name.lower():
                                if link_col_name:
                                    link_cell = row_dict.setdefault(
                                        link_col_name, {"text": "", "widget_text": ""}
                                    )
                                    link_cell["text"] = link_status
                                    link_cell["widget_text"] = link_status
                                break
                    continue

                row_data = {}
                for col_obj in self.active_columns:
                    cell_info: dict = {"text": ""}
                    if isinstance(col_obj, PortSearchColumn):
                        cell_info["text"] = port_name
                    elif isinstance(col_obj, LinkColumn):
                        cell_info["text"] = link_status
                        cell_info["widget_text"] = link_status
                    elif isinstance(col_obj, PortStateColumn):
                        cell_info["text"] = "In Work"
                        cell_info["widget_text"] = "In Work"
                    row_data[col_obj.name] = cell_info

                model.data_cache["rows"].append(row_data)
                existing_ports.add(port_name.lower())
                new_rows_count += 1

            total_imported_ports += new_rows_count
            if new_rows_count > 0:
                touched_models.append(model)

        self.list_model.refresh()

        # Eagerly populate the (Match) columns against the active matcher for
        # every model that received rows — not just the active one — so imported
        # rows show real fuzzy results instead of the lazy placeholder.
        self._eager_match_imported_models(touched_models)

        if self.main_window.current_project_file:
            success, msg = ProjectSaver.save_project(
                self.main_window, self.main_window.current_project_file
            )
            if not success:
                QtWidgets.QMessageBox.warning(
                    self.main_window, "Save Warning",
                    f"Import completed but project could not be saved:\n{msg}",
                )
                return

        QtWidgets.QMessageBox.information(
            self.main_window,
            "Import Completed",
            f"Import finished successfully.\nTotal new ports imported: {total_imported_ports}",
        )

    # ------------------------------------------------------------------
    # Rhapsody path-based import
    # ------------------------------------------------------------------

    def _import_rhapsody(self, file_path: str, path_col: str):
        """
        Handles Rhapsody-exported CSV/XLSX files where architecture models are
        derived from the full path column and only P10_SW_Arch_Public rows are
        imported.  Multi-operation cells expand into one row per operation.
        """
        from Application_Logic.Logic_Rhapsody_Import import (
            read_file, get_model_preview, build_import_data,
            detect_required_interface_col,
        )
        from UI.Dialog_Rhapsody_Import import RhapsodyImportDialog

        try:
            columns, rows = read_file(file_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window, "Import Error",
                f"Failed to read file:\n{e}"
            )
            return

        # Detect the "Required Interface" source column so rows with a blank
        # required interface (provided-port stubs) can be discarded on import.
        required_col = detect_required_interface_col(columns, path_col)
        model_preview = get_model_preview(rows, path_col, required_col)
        if not model_preview:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Import Warning",
                "No P10_SW_Arch_Public rows found in this file."
            )
            return

        # Auto-detect operations column: first non-path column with embedded newlines
        ops_col = None
        for col in columns:
            if col == path_col:
                continue
            for row in rows[:30]:
                val = str(row.get(col, ""))
                if "\n" in val or "\r\n" in val:
                    ops_col = col
                    break
            if ops_col:
                break

        existing_table_col_names = [col.name for col in self.active_columns]
        existing_model_names = [m.name for m in self.model_manager.models if not m.is_deleted]

        dialog = RhapsodyImportDialog(
            file_path=file_path,
            columns=columns,
            rows=rows,
            path_col=path_col,
            ops_col=ops_col,
            model_preview=model_preview,
            existing_table_cols=existing_table_col_names,
            existing_model_names=existing_model_names,
            parent=self.main_window,
        )
        if not dialog.exec():
            return

        col_mapping = dialog.col_mapping
        model_mapping = dialog.model_mapping
        new_columns = dialog.new_columns

        if not col_mapping:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Import Warning",
                "No columns were selected for import."
            )
            return

        # 1. Create any new table columns
        for col_name in new_columns:
            if not any(c[0] == col_name for c in self.active_config):
                self.active_config.append((col_name, "Static Text", True))
        if new_columns:
            self._rebuild_column_objects()
            self._setup_table_style()

        # 2. Build {model_name -> [row_dicts]}
        # Determine which source column is the operations column (may have been
        # remapped to any table column name, but source key is still ops_col).
        import_data = build_import_data(rows, col_mapping, path_col, ops_col, required_col)

        # 3. Store the ops table-column name on the DB so test case design can
        #    find it for grouping later.
        ops_tbl_col = col_mapping.get(ops_col) if ops_col else None
        if ops_tbl_col and hasattr(self.main_window, 'project_db'):
            db = self.main_window.project_db
            if db and db.is_open:
                db.set_meta("operations_column_name", ops_tbl_col)

        total_imported = 0
        touched_models = []

        for extracted_name, table_rows in import_data.items():
            target_name = model_mapping.get(extracted_name, "<Create New>")

            if target_name == "<Create New>":
                existing_names = [m.name for m in self.model_manager.models]
                unique_name = extracted_name
                counter = 1
                while unique_name in existing_names:
                    unique_name = f"{extracted_name}_{counter}"
                    counter += 1
                model = self.model_manager.create_model(unique_name, "In Work")
                if not model.data_cache:
                    model.data_cache = {"rows": []}
            else:
                model = next(
                    (m for m in self.model_manager.models if m.name == target_name), None
                )
                if not model:
                    continue
                if model == self.model_manager.get_active_model():
                    self.flush_current_data_to_model()
                if not model.data_cache:
                    model.data_cache = {"rows": []}

            # Build dedup set: (port_text, operation_text) pairs
            port_col_name = next(
                (c.name for c in self.active_columns if isinstance(c, PortSearchColumn)), None
            )
            existing_keys: set = set()
            for existing_row in model.data_cache.get("rows", []):
                port_val = existing_row.get(port_col_name, {}).get("text", "").strip().lower() if port_col_name else ""
                op_val = existing_row.get(ops_tbl_col, {}).get("text", "").strip().lower() if ops_tbl_col else ""
                existing_keys.add((port_val, op_val))

            new_count = 0
            for row_dict in table_rows:
                port_val = row_dict.get(port_col_name, {}).get("text", "").strip().lower() if port_col_name else ""
                op_val = row_dict.get(ops_tbl_col, {}).get("text", "").strip().lower() if ops_tbl_col else ""
                if (port_val, op_val) in existing_keys:
                    continue

                # Fill columns not in the mapping with sensible defaults
                full_row = {}
                for col_obj in self.active_columns:
                    if col_obj.name in row_dict:
                        full_row[col_obj.name] = row_dict[col_obj.name]
                    elif isinstance(col_obj, PortStateColumn):
                        full_row[col_obj.name] = {"text": "In Work", "widget_text": "In Work"}
                    elif isinstance(col_obj, LinkColumn):
                        full_row[col_obj.name] = {"text": "No", "widget_text": "No"}
                    else:
                        full_row[col_obj.name] = {"text": ""}

                model.data_cache["rows"].append(full_row)
                existing_keys.add((port_val, op_val))
                new_count += 1

            total_imported += new_count
            if new_count > 0:
                touched_models.append(model)

        self.list_model.refresh()

        # Eagerly populate the (Match) columns against the active matcher for
        # every model that received operations — not just the active one — so
        # imported rows show real fuzzy results instead of the lazy placeholder.
        self._eager_match_imported_models(touched_models)

        if self.main_window.current_project_file:
            success, msg = ProjectSaver.save_project(
                self.main_window, self.main_window.current_project_file
            )
            if not success:
                QtWidgets.QMessageBox.warning(
                    self.main_window, "Save Warning",
                    f"Import completed but project could not be saved:\n{msg}"
                )
                return

        QtWidgets.QMessageBox.information(
            self.main_window,
            "Import Completed",
            f"Rhapsody import finished.\nTotal new rows imported: {total_imported}"
        )

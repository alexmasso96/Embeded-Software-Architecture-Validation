"""
Architecture Table — Excel Import Mixin
Handles import_architecture_excel and the word-similarity helper it relies on.
"""
import json
import os
import re

from PyQt6 import QtWidgets
from fuzzywuzzy import fuzz

from .Logic_Column_Types import PortSearchColumn, LinkColumn, PortStateColumn
from .Logic_Project_Saving import ProjectSaver
from UI.Dialog_Architecture_Import import (
    ImportModeDialog,
    ManualImportDialog,
    FuzzyMatchPromptDialog,
    ImportConfirmationDialog,
)


class ArchitectureImportMixin:

    def calculate_word_similarity(self, name1: str, name2: str) -> float:
        """
        Word-based similarity: splits camelCase/underscores/dashes and matches
        word-by-word.  Words ≤ 2 chars need an exact match; longer words use
        fuzzywuzzy ratio with a threshold of 85.
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
        Imports software architecture ports from an Excel file.
        Runs a dialog state-machine (Mode → Manual → Confirm) then performs
        the actual import into model caches.
        """
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Import Excel File", "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        self.flush_current_data_to_model()

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
                print(f"Error reading sheet {sheet_name}: {e}")
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

            if model.file_path:
                try:
                    os.makedirs(os.path.dirname(model.file_path), exist_ok=True)
                    with open(model.file_path, 'w') as f:
                        json.dump(model.data_cache, f, indent=4)
                except Exception as e:
                    print(f"Failed to write model file: {e}")

        self.list_model.refresh()
        self.load_active_model_to_table()

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

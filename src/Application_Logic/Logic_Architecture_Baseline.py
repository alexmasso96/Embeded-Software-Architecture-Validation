"""
Architecture Table — Baseline Mixin
Handles creating, loading, and exiting baseline snapshots.
All data lives in the ProjectDatabase — no file copying needed.
"""
import json
import logging

from PyQt6 import QtWidgets

logger = logging.getLogger(__name__)

from .Logic_Project_Saving import ProjectSaver


class ArchitectureBaselineMixin:

    def get_current_layout_data(self):
        """Returns the full layout dict (columns, settings, test-case design)."""
        full_table_data = self.get_project_data()
        layout_data = full_table_data.get("config", [])
        settings_data = full_table_data.get("settings", {})

        test_case_json = {}
        if hasattr(self.main_window, 'test_case_controller'):
            test_case_json = {
                "project_title": self.main_window.test_case_controller.get_project_title(),
                "design_template": self.main_window.test_case_controller.get_design_template(),
            }

        return {
            "version": "2.0",
            "layout": layout_data,
            "settings": settings_data,
            "test_case_design": test_case_json,
        }

    def handle_create_baseline(self):
        if not self.release_manager.project_path:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Warning",
                "Please save or load a project before creating a baseline."
            )
            return

        active_idx = self.release_manager.active_release_index
        if active_idx == -1:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Warning", "No active release to baseline."
            )
            return

        active_release = self.release_manager.get_active_release()
        if active_release.is_baseline:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Warning",
                "Cannot create a baseline from a baseline."
            )
            return

        name, ok = QtWidgets.QInputDialog.getText(
            self.main_window, "Create Baseline", "Enter Baseline Name:"
        )
        if not ok or not name.strip():
            return

        try:
            self.flush_current_data_to_model()

            full_table_data = self.get_project_data()
            rows_data = full_table_data.get("rows", [])

            active_model_data = {
                "rows": rows_data,
                "column_metadata": self.column_metadata,
            }
            active_model = self.model_manager.get_active_model()
            if active_model and active_model.data_cache:
                active_model_data["release_results"] = active_model.data_cache.get(
                    "release_results", {}
                )

            layout_data = self.get_current_layout_data()
            baseline = self.release_manager.create_baseline(
                active_idx, name.strip(), layout_data, active_model_data
            )

            success, save_msg = ProjectSaver.save_project(
                self.main_window, self.release_manager.project_path
            )
            if not success:
                logger.warning("Project save during baseline creation failed: %s", save_msg)

            self.refresh_all_column_locking()

            QtWidgets.QMessageBox.information(
                self.main_window, "Success", f"Created Baseline: {baseline.name}"
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window, "Error", f"Failed to create baseline: {e}"
            )

    def handle_load_baseline(self):
        if not self.release_manager.project_path:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Warning",
                "Please save or load a project before loading a baseline."
            )
            return

        baselines = [r for r in self.release_manager.releases
                     if r.is_baseline and not r.is_deleted]
        if not baselines:
            QtWidgets.QMessageBox.information(
                self.main_window, "Load Baseline", "No baselines available to load."
            )
            return

        name, ok = QtWidgets.QInputDialog.getItem(
            self.main_window, "Load Baseline", "Select a baseline to load:",
            [b.name for b in baselines], 0, False
        )
        if not ok or not name:
            return

        selected_baseline = next(b for b in baselines if b.name == name)
        self.load_baseline_by_model(selected_baseline)

    def load_baseline_by_model(self, selected_baseline):
        if ProjectSaver.has_temp_changes(self.release_manager.project_path):
            reply = QtWidgets.QMessageBox.question(
                self.main_window,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before loading the baseline?\n\n"
                "Yes - Save changes\nNo - Discard changes\nCancel - Cancel loading",
                (QtWidgets.QMessageBox.StandardButton.Yes |
                 QtWidgets.QMessageBox.StandardButton.No |
                 QtWidgets.QMessageBox.StandardButton.Cancel),
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                success, msg = ProjectSaver.save_project(
                    self.main_window, self.release_manager.project_path
                )
                if not success:
                    QtWidgets.QMessageBox.critical(
                        self.main_window, "Save Error", f"Could not save project: {msg}"
                    )
                    return
            elif reply == QtWidgets.QMessageBox.StandardButton.No:
                ProjectSaver.cleanup_temp(self.release_manager.project_path)
            else:
                return

        self.table.setVisible(False)

        from .Logic_Loading_Window import LoadingDialog
        loader = LoadingDialog(self.main_window)
        loader.ui.lbl_loading_text.setText(f"Loading baseline {selected_baseline.name}...")
        loader.show()
        QtWidgets.QApplication.processEvents()

        try:
            db = getattr(self.main_window, 'project_db', None)

            # Load baseline data from DB
            baseline_data = self.release_manager._load_data(selected_baseline)
            rows = baseline_data.get("rows", [])

            # Load layout stored at baseline creation time
            layout_blob = None
            if db and db.is_open and selected_baseline.id:
                layout_blob = db.get_meta(f"baseline_layout_{selected_baseline.id}")

            if layout_blob:
                try:
                    layout_json = json.loads(layout_blob)
                except Exception:
                    layout_json = {}
            else:
                layout_json = {}

            layout_config = layout_json.get("layout", [])
            settings_config = layout_json.get("settings", {})
            test_case_data = layout_json.get("test_case_design", {})

            self.btn_exit_baseline.setVisible(True)

            if layout_config:
                self.active_config = [tuple(c) for c in layout_config]
                self._rebuild_column_objects()
                self.current_default_cyclicity = settings_config.get("default_cyclicity", "10")
                self.show_retired = settings_config.get("show_retired", True)
                self.show_deleted = settings_config.get("show_deleted", False)
                self._setup_table_style()

            data_to_load = {
                "config": layout_config or self.active_config,
                "settings": settings_config,
                "rows": rows,
            }
            self.load_project_data(data_to_load)

            if test_case_data and hasattr(self.main_window, 'test_case_controller'):
                self.main_window.test_case_controller.load_data(test_case_data)

            # Load ELF for this baseline (shared from DB)
            if selected_baseline.elf_hash and db and db.is_open:
                from core.elf_parser import ELFParser
                parser = ELFParser()
                parser.load_from_db(db, selected_baseline.elf_hash)
                self.main_window.parser = parser
                from Application_Logic.Logic_Symbol_Matcher import SymbolMatcher
                self.matcher = SymbolMatcher(
                    parser, db=db, elf_hash=selected_baseline.elf_hash
                )

            self.table.setEditTriggers(
                QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
            )
            self.main_window.setWindowTitle(
                f"Architecture Testing Tool - {selected_baseline.name} (BASELINE - READ ONLY)"
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window, "Error", f"Failed to load baseline: {e}"
            )
        finally:
            loader.close()
            self.table.setVisible(True)

    def handle_exit_baseline(self):
        self.table.setVisible(False)

        from .Logic_Loading_Window import LoadingDialog
        loader = LoadingDialog(self.main_window)
        loader.ui.lbl_loading_text.setText("Exiting Baseline View, restoring project...")
        loader.show()
        QtWidgets.QApplication.processEvents()

        try:
            self.btn_exit_baseline.setVisible(False)
            if self.release_manager.project_path:
                ProjectSaver.load_project(
                    self.main_window, self.release_manager.project_path
                )
            self.main_window.set_app_mode(self.main_window.edit_mode)
            self.refresh_all_column_locking()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.main_window, "Error", f"Failed to exit baseline view: {e}"
            )
        finally:
            loader.close()
            self.table.setVisible(True)

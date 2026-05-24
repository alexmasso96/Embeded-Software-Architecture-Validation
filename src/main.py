import sys
import os
import json

# Optional: Ensure local imports work if running directly from this folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPalette, QColor
from PyQt6 import QtWidgets, QtGui, QtCore
import UI
import Application_Logic as App_Logic
from Application_Logic.Logic_Project_Saving import ProjectSaver

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Default edit mode property
        self.edit_mode = True

        # Instantiate the generated UI class
        self.ui = UI.Ui_MainWindow()
        
        # Set up the user interface on this QMainWindow instance
        self.ui.setupUi(self)

        # Initialize the specialized controllers
        self.arch_controller = App_Logic.ArchitectureTabController(self)
        self.test_case_controller = App_Logic.TestCaseDesignController(self)
        
        #initialize parser storage
        self.parser = None

        #Connect Menu Actions
        self.ui.mnu_New_Project.triggered.connect(self.new_project)
        self.ui.actionSave.triggered.connect(self.save_project)
        self.ui.actionSave_project_as.triggered.connect(self.save_project_as)
        self.ui.mnu_Load_Project.triggered.connect(self.load_project)
        self.ui.mnu_Import_Architecture_Export.triggered.connect(self.arch_controller.import_architecture_excel)
        
        # Dynamic Edit Menu addition
        self.menuEdit = QtWidgets.QMenu("&Edit", self.ui.menubar)
        self.ui.menubar.insertMenu(self.ui.menuAbout.menuAction(), self.menuEdit)
        
        self.actionOpen_Exclusive_Edit = QtGui.QAction("Open in Exclusive Edit", self)
        self.actionRelease_Lock = QtGui.QAction("Release Lock & Switch to View Only", self)
        self.actionHelp_Edit_Modes = QtGui.QAction("Help: Edit Modes", self)
        
        self.menuEdit.addAction(self.actionOpen_Exclusive_Edit)
        self.menuEdit.addAction(self.actionRelease_Lock)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionHelp_Edit_Modes)
        
        self.actionOpen_Exclusive_Edit.triggered.connect(self.switchToExclusiveEdit)
        self.actionRelease_Lock.triggered.connect(self.switchToViewOnly)
        self.actionHelp_Edit_Modes.triggered.connect(self.showEditModesHelp)

        # Dynamic Options Menu addition (Feature 2 & 6)
        self.menuOptions = QtWidgets.QMenu("&Options", self.ui.menubar)
        self.ui.menubar.insertMenu(self.ui.menuAbout.menuAction(), self.menuOptions)
        
        # Auto-Save Submenu
        self.menuAutoSave = QtWidgets.QMenu("Auto Save Interval", self)
        self.menuOptions.addMenu(self.menuAutoSave)
        
        from PyQt6.QtGui import QActionGroup
        self.auto_save_group = QActionGroup(self)
        self.auto_save_group.setExclusive(True)
        
        self.act_save_immediate = QtGui.QAction("Immediate", self, checkable=True)
        self.act_save_1min = QtGui.QAction("1 Minute", self, checkable=True)
        self.act_save_5min = QtGui.QAction("5 Minutes", self, checkable=True)
        self.act_save_15min = QtGui.QAction("15 Minutes", self, checkable=True)
        self.act_save_disabled = QtGui.QAction("Do Not Auto Save", self, checkable=True)
        
        self.auto_save_group.addAction(self.act_save_immediate)
        self.auto_save_group.addAction(self.act_save_1min)
        self.auto_save_group.addAction(self.act_save_5min)
        self.auto_save_group.addAction(self.act_save_15min)
        self.auto_save_group.addAction(self.act_save_disabled)
        
        self.menuAutoSave.addAction(self.act_save_immediate)
        self.menuAutoSave.addAction(self.act_save_1min)
        self.menuAutoSave.addAction(self.act_save_5min)
        self.menuAutoSave.addAction(self.act_save_15min)
        self.menuAutoSave.addAction(self.act_save_disabled)
        
        self.auto_save_map = {
            self.act_save_immediate: "immediate",
            self.act_save_1min: "1min",
            self.act_save_5min: "5min",
            self.act_save_15min: "15min",
            self.act_save_disabled: "disabled"
        }
        self.auto_save_group.triggered.connect(self.change_auto_save_interval)
        
        # Test Mode QActions
        self.actionEnter_Test_Mode = QtGui.QAction("Enter Test Mode", self)
        self.actionExit_Test_Mode = QtGui.QAction("Exit Test Mode", self)
        self.actionExit_Test_Mode.setVisible(False)
        self.actionView_All_Baselines = QtGui.QAction("View All Baselines", self)
        
        self.menuOptions.addSeparator()
        self.menuOptions.addAction(self.actionEnter_Test_Mode)
        self.menuOptions.addAction(self.actionExit_Test_Mode)
        self.menuOptions.addAction(self.actionView_All_Baselines)
        
        self.actionEnter_Test_Mode.triggered.connect(self.enter_test_mode)
        self.actionExit_Test_Mode.triggered.connect(self.exit_test_mode)
        self.actionView_All_Baselines.triggered.connect(self.show_all_baselines_dialog)

        # Dynamic History Menu addition (Feature 5)
        self.menuHistory = QtWidgets.QMenu("&History", self.ui.menubar)
        self.ui.menubar.insertMenu(self.ui.menuAbout.menuAction(), self.menuHistory)
        
        self.actionView_History = QtGui.QAction("View History", self)
        self.menuHistory.addAction(self.actionView_History)
        self.actionView_History.triggered.connect(self.show_history_dialog)

        # Default values and timer startup
        self.test_mode = False
        self.master_password_hash = None
        self.set_auto_save_interval("immediate")

        # Connect Sidebar Actions
        self.ui.SellectSoftware_Release.clicked.connect(self.handle_select_release)

        # Connect Tab Widget Actions
        self.ui.tabWidget.currentChanged.connect(self.test_case_controller.on_tab_changed)

        # Current Project File
        self.current_project_file = None
        self._has_unsaved_new_project = False

        # Always open on the Architecture tab (index 0), not whatever Qt Designer last saved
        self.ui.tabWidget.setCurrentIndex(0)

        # Trigger startup launcher dialog after the window is shown
        QTimer.singleShot(100, self.show_startup_launcher)

    def show_startup_launcher(self):
        """Displays the Startup Launcher dialog."""
        from UI.Dialog_Startup_Launcher import StartupLauncherDialog
        dialog = StartupLauncherDialog(self)
        dialog.exec()

    def check_unsaved_changes(self) -> bool:
        """Prompts the user to save unsaved changes. Returns True if okay to proceed, False to cancel."""
        if getattr(self, '_has_unsaved_new_project', False) and not self.current_project_file:
            reply = QMessageBox.question(
                self,
                "Unsaved Project",
                "You have unsaved changes in a new project. Do you want to save them before proceeding?\n\n"
                "Yes - Save project.\n"
                "No - Discard project.\n"
                "Cancel - Cancel operation.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_project_as()
                if self.current_project_file is None:
                    return False
                return True
            elif reply == QMessageBox.StandardButton.No:
                self._has_unsaved_new_project = False
                return True
            else:
                return False

        if self.current_project_file and ProjectSaver.has_temp_changes(self.current_project_file):
            reply = QMessageBox.question(
                self, 
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before proceeding?\n\n"
                "Yes - Save changes.\n"
                "No - Discard changes.\n"
                "Cancel - Cancel operation.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, msg = ProjectSaver.save_project(self, self.current_project_file)
                if success:
                    return True
                else:
                    QMessageBox.critical(self, "Save Error", f"Could not save project: {msg}")
                    return False
            elif reply == QMessageBox.StandardButton.No:
                ProjectSaver.cleanup_temp(self.current_project_file)
                return True
            else:
                return False
        return True

    def set_app_mode(self, edit_mode: bool):
        """Switches application mode between View-Only and Exclusive Edit."""
        self.edit_mode = edit_mode
        
        # 1. Update Window Title
        if self.current_project_file:
            base_name = os.path.basename(self.current_project_file)
            mode_str = "Exclusive Edit" if edit_mode else "View Only"
            self.setWindowTitle(f"Architecture Testing Tool - {base_name} ({mode_str})")
        else:
            self.setWindowTitle("Architecture Testing Tool")
            
        # 2. Enable/disable menu items
        self.ui.actionSave.setEnabled(edit_mode)
        self.ui.actionSave_project_as.setEnabled(edit_mode)
        self.ui.mnu_New_Project.setEnabled(edit_mode)
        self.ui.mnu_Import_Architecture_Export.setEnabled(edit_mode)
        
        # 3. Enable/disable sidebar actions
        self.ui.SideBar_Architecture_Generate_Btn.setEnabled(edit_mode)
        self.ui.SellectSoftware_Release.setEnabled(edit_mode)
        
        if hasattr(self.arch_controller, 'btn_create_baseline'):
            self.arch_controller.btn_create_baseline.setEnabled(edit_mode)
            
        # 4. Enable/disable Table cells and custom widgets
        if edit_mode:
            # Re-enable double click editing on table
            self.ui.Architecture_Table.setEditTriggers(
                QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
                QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            )
        else:
            # Disable double click editing
            self.ui.Architecture_Table.setEditTriggers(
                QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
            )
            
        # Refresh current row widgets and items to apply Enabled/Disabled state
        if hasattr(self.arch_controller, 'active_columns'):
            self.ui.Architecture_Table.blockSignals(True)
            for row in range(self.ui.Architecture_Table.rowCount()):
                for col_idx, col_obj in enumerate(self.arch_controller.active_columns):
                    widget = self.ui.Architecture_Table.cellWidget(row, col_idx)
                    if widget:
                        widget.setEnabled(edit_mode)
                        # Fix: Explicitly re-enable the lineEdit of editable combo boxes
                        if edit_mode and isinstance(widget, QtWidgets.QComboBox) and widget.isEditable():
                            widget.lineEdit().setEnabled(True)
                            widget.lineEdit().setReadOnly(False)
                    item = self.ui.Architecture_Table.item(row, col_idx)
                    if item:
                        if not widget:  # Only allow inline editing for cells without a cell widget
                            if edit_mode:
                                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                            else:
                                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                        else:
                            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.Architecture_Table.blockSignals(False)
                            
        # 5. Disable editing in Test Case Design tab
        if hasattr(self, 'test_case_controller'):
            self.test_case_controller.txt_project_title.setReadOnly(not edit_mode)
            self.test_case_controller.txt_test_case_design.setReadOnly(not edit_mode)
            
        # 6. Update Edit menu actions
        self.update_edit_menu()

        # 7. Apply column-specific dynamic locking/unlocking rules (e.g. baseline locks)
        if hasattr(self, 'arch_controller') and hasattr(self.arch_controller, 'refresh_all_column_locking'):
            self.arch_controller.refresh_all_column_locking()

    def update_edit_menu(self):
        """Updates the text and enabled states of the dynamic Edit menu items."""
        if not self.current_project_file:
            self.actionOpen_Exclusive_Edit.setEnabled(False)
            self.actionOpen_Exclusive_Edit.setText("Open in Exclusive Edit")
            self.actionRelease_Lock.setEnabled(False)
            return

        from Application_Logic.Logic_File_Locking import FileLockManager
        lock_status = FileLockManager.check_lock(self.current_project_file)
        
        if lock_status["status"] == "unlocked":
            self.actionOpen_Exclusive_Edit.setEnabled(True)
            self.actionOpen_Exclusive_Edit.setText("Open in Exclusive Edit")
            self.actionRelease_Lock.setEnabled(False)
        elif lock_status["status"] == "locked_by_me":
            self.actionOpen_Exclusive_Edit.setEnabled(False)
            self.actionOpen_Exclusive_Edit.setText("Open in Exclusive Edit")
            self.actionRelease_Lock.setEnabled(True)
        elif lock_status["status"] == "locked_by_other":
            user = lock_status["user"]
            self.actionOpen_Exclusive_Edit.setEnabled(False)
            self.actionOpen_Exclusive_Edit.setText(f"Open in Exclusive Edit — Locked by {user}")
            self.actionRelease_Lock.setEnabled(False)

    def switchToExclusiveEdit(self):
        """Triggers lock acquisition and switches to Edit mode."""
        if not self.current_project_file:
            return
            
        from Application_Logic.Logic_File_Locking import FileLockManager
        success, lock_info = FileLockManager.acquire_lock(self.current_project_file)
        if success:
            self.set_app_mode(True)
            self.ui.statusbar.showMessage("Project switched to Exclusive Edit mode.")
        else:
            QMessageBox.critical(self, "Project Locked", f"Could not acquire exclusive lock.\n\n{lock_info}")

    def switchToViewOnly(self):
        """Releases the held lock and switches to View-Only mode."""
        if not self.current_project_file:
            return
            
        # Perform dirty check
        if not self.check_unsaved_changes():
            return
            
        # Automatically deactivate test mode (Feature 6)
        if getattr(self, 'test_mode', False):
            self.exit_test_mode()
            
        from Application_Logic.Logic_File_Locking import FileLockManager
        FileLockManager.release_lock(self.current_project_file)
        self.set_app_mode(False)
        self.ui.statusbar.showMessage("Project switched to View-Only mode.")

    def showEditModesHelp(self):
        """Displays documentation regarding View-Only and Exclusive Edit modes."""
        QMessageBox.information(
            self,
            "Help: Edit Modes",
            "View Only Mode: You can browse the project, switch between architecture models, and view baselines, but cannot make any changes.\n\n"
            "Exclusive Edit Mode: Acquires a lock on the project so only one user can edit at a time. Other users will see the project as locked and can only open it in View Only mode.\n\n"
            "The lock is automatically released when you close the application or switch to View Only mode."
        )

    def write_lock_heartbeat(self):
        """Calls FileLockManager.write_heartbeat if editing an open project."""
        if self.current_project_file and getattr(self, 'edit_mode', False):
            from Application_Logic.Logic_File_Locking import FileLockManager
            FileLockManager.write_heartbeat(self.current_project_file)

    def handle_select_release(self):
        # Open the release selection dialog
        from UI.Dialog_Release_Selection import ReleaseSelectionDialog
        
        # We pass the release_manager from the controller
        dialog = ReleaseSelectionDialog(self.arch_controller.release_manager, self.arch_controller, self)
        dialog.exec()

    def new_project(self):
        """
        Handler for the 'New Project' menu item
        """
        if not self.check_unsaved_changes():
            return

        # Release previous lock if held
        if self.current_project_file and getattr(self, 'edit_mode', True):
            from Application_Logic.Logic_File_Locking import FileLockManager
            FileLockManager.release_lock(self.current_project_file)

        dialog = App_Logic.NewProjectController(self)

        if dialog.exec():
            # Prompt user to set a master password (Feature 1)
            from Application_Logic.Logic_Security import MasterPasswordSetupDialog
            pw_dialog = MasterPasswordSetupDialog(self)
            if pw_dialog.exec():
                password = pw_dialog.get_password()
                from Application_Logic.Logic_Security import SecurityManager
                self.master_password_hash = SecurityManager.hash_password(password)
            else:
                QMessageBox.warning(self, "Cancelled", "Project creation cancelled because a master password is required.")
                return

            # Reset existing controller state first!
            self.arch_controller.is_loading = True
            self.arch_controller.reset_controller()
            ProjectSaver._cached_elf_data = None
            ProjectSaver._cached_parser_hash = None
            self.arch_controller.is_loading = False

            # if the user loaded a file, we grab the parser form dialog
            self.parser = dialog.parser
            self.ui.statusbar.showMessage("Project initialized successfully.")

            # Pass the data to the controller
            # dialog.release_name is captured in Logic_New_Project
            self.arch_controller.populate_from_parser(self.parser, release_name=dialog.release_name)
            self.current_project_file = None
            self._has_unsaved_new_project = True

            # New projects are initialized in Edit Mode
            self.set_app_mode(True)

            # Ask where to save immediately so auto-save and dirty-tracking work from the start
            self.save_project_as()

    def save_project(self):
        if self.current_project_file:
            success, msg = ProjectSaver.save_project(self, self.current_project_file)
            self.ui.statusbar.showMessage(msg)
            if not success:
                QMessageBox.critical(self, "Save Error", msg)
        else:
            self.save_project_as()

    def save_project_as(self):
        # We ask for a "filename" which will become the Directory Name
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project (Creates Folder)", "", "Architecture Project (*.arch)")
        if file_path:
            # We keep the .arch extension convention for the folder
            if not file_path.endswith(".arch"):
                file_path += ".arch"
            
            os.makedirs(file_path, exist_ok=True)
            
            # If we already held a lock on a previous project, we do NOT release it yet,
            # because we are saving the *current* state as a new project path.
            # But the new project path must acquire a lock for us to continue in edit mode!
            from Application_Logic.Logic_File_Locking import FileLockManager
            success, lock_info = FileLockManager.acquire_lock(file_path)
            if not success:
                QMessageBox.critical(self, "Lock Error", f"Cannot acquire lock on new project path: {lock_info}")
                return

            # Release previous project lock since we are transitioning to the new path
            if self.current_project_file and getattr(self, 'edit_mode', True):
                FileLockManager.release_lock(self.current_project_file)

            success, msg = ProjectSaver.save_project(self, file_path)
            self.ui.statusbar.showMessage(msg)
            if success:
                self.current_project_file = file_path
                self._has_unsaved_new_project = False
                self.set_app_mode(True)
            else:
                # If save failed, release lock we just acquired on new path
                FileLockManager.release_lock(file_path)
                QMessageBox.critical(self, "Save Error", msg)

    def closeEvent(self, event):
        """
        Handle application close event to check for unsaved changes (temp file).
        """
        if self.current_project_file and ProjectSaver.has_temp_changes(self.current_project_file):
            reply = QMessageBox.question(
                self, 
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before exiting?\n\n"
                "Yes - Save changes to project.\n"
                "No - Discard changes.\n"
                "Cancel - Stay in application.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, msg = ProjectSaver.save_project(self, self.current_project_file)
                if success:
                    # Release lock before close
                    if getattr(self, 'edit_mode', True):
                        from Application_Logic.Logic_File_Locking import FileLockManager
                        FileLockManager.release_lock(self.current_project_file)
                    event.accept()
                else:
                    QMessageBox.critical(self, "Save Error", f"Could not save project: {msg}")
                    event.ignore()
            
            elif reply == QMessageBox.StandardButton.No:
                # Discard changes -> cleanup temp file
                ProjectSaver.cleanup_temp(self.current_project_file)
                # Release lock before close
                if getattr(self, 'edit_mode', True):
                    from Application_Logic.Logic_File_Locking import FileLockManager
                    FileLockManager.release_lock(self.current_project_file)
                event.accept()
            
            else:
                event.ignore()
        else:
            # Release lock before close
            if self.current_project_file and getattr(self, 'edit_mode', True):
                from Application_Logic.Logic_File_Locking import FileLockManager
                FileLockManager.release_lock(self.current_project_file)
            event.accept()

    def load_project(self):
        if not self.check_unsaved_changes():
            return
            
        file_path = QFileDialog.getExistingDirectory(self, "Load Project Folder", "")
        if not file_path:
            return

        reply = QMessageBox.question(
            self,
            "Select Open Mode",
            "Do you want to open this project in Exclusive Edit mode?\n\n"
            "Yes - Attempt to lock and open in Edit mode.\n"
            "No - Open in View-Only mode.\n"
            "Cancel - Do not load.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            from Application_Logic.Logic_File_Locking import FileLockManager
            success, lock_info = FileLockManager.acquire_lock(file_path)
            if success:
                self.load_project_with_mode(file_path, edit_mode=True)
            else:
                QMessageBox.critical(self, "Project Locked", f"Could not open project in Exclusive Edit mode.\n\n{lock_info}")
        elif reply == QMessageBox.StandardButton.No:
            self.load_project_with_mode(file_path, edit_mode=False)

    def load_project_with_mode(self, file_path, edit_mode):
        # check_unsaved_changes is called by all public callers before invoking this method.

        # Release previous lock if held
        if self.current_project_file and getattr(self, 'edit_mode', True):
            from Application_Logic.Logic_File_Locking import FileLockManager
            FileLockManager.release_lock(self.current_project_file)

        # Issue: Clean up any stale temp files from previous sessions for THIS loaded project
        ProjectSaver.cleanup_temp(file_path)
        ProjectSaver._cached_elf_data = None
        ProjectSaver._cached_parser_hash = None

        self.integrity_mismatch = False
        success, msg = ProjectSaver.load_project(self, file_path)
        
        if success:
            if getattr(self, 'integrity_mismatch', False):
                # Prompt the user for master password (Feature 4)
                from Application_Logic.Logic_Security import MasterPasswordPromptDialog, SecurityManager
                
                # Read stored password hash from layout.json
                layout_path = os.path.join(file_path, "layout.json")
                master_password_hash = None
                if os.path.exists(layout_path):
                    try:
                        with open(layout_path, 'r') as f:
                            layout_json = json.load(f)
                        master_password_hash = layout_json.get("master_password_hash")
                    except Exception:
                        pass
                
                if master_password_hash:
                    authenticated = False
                    for attempt in range(3):
                        prompt_dialog = MasterPasswordPromptDialog(self, "Integrity Mismatch Detected. Enter Master Password:")
                        if prompt_dialog.exec():
                            entered_password = prompt_dialog.get_password()
                            if SecurityManager.verify_password(entered_password, master_password_hash):
                                authenticated = True
                                break
                            else:
                                QMessageBox.warning(self, "Invalid Password", f"Incorrect password. Attempt {attempt + 1} of 3.")
                        else:
                            break # Cancelled
                    
                    if not authenticated:
                        if edit_mode:
                            from Application_Logic.Logic_File_Locking import FileLockManager
                            FileLockManager.release_lock(file_path)
                        
                        self.current_project_file = None
                        self.arch_controller.reset_controller()
                        self.setWindowTitle("Architecture Testing Tool")
                        QMessageBox.critical(self, "Integrity Error", "Project loading cancelled due to integrity validation failure.")
                        self.ui.statusbar.showMessage("Project load failed due to integrity mismatch.")
                        return
                else:
                    # No master password set (legacy project)
                    # Show a warning and allow user to proceed
                    QMessageBox.warning(self, "Integrity Warning", 
                                        "Project integrity verification failed (missing hash/metadata) and no master password is set.\n"
                                        "This may indicate a legacy project or possible tampering. Proceeding to open.")
            
            # If successfully opened, apply master_password_hash & auto_save_interval
            self.current_project_file = file_path
            self.set_app_mode(edit_mode)
            
            # Read settings to apply master_password_hash & auto-save
            layout_path = os.path.join(file_path, "layout.json")
            if os.path.exists(layout_path):
                try:
                    with open(layout_path, 'r') as f:
                        layout_json = json.load(f)
                    self.master_password_hash = layout_json.get("master_password_hash")
                    
                    # Apply auto-save interval from layout.json settings if exists
                    settings_conf = layout_json.get("settings", {})
                    auto_save_val = settings_conf.get("auto_save_interval", "immediate")
                    self.set_auto_save_interval(auto_save_val)
                except Exception:
                    pass
            self.ui.statusbar.showMessage(msg)
        else:
            QMessageBox.critical(self, "Load Error", msg)

    def change_auto_save_interval(self, action):
        interval_str = self.auto_save_map.get(action, "immediate")
        self.set_auto_save_interval(interval_str)
        if self.current_project_file and getattr(self, 'edit_mode', True):
            self.save_project()

    def set_auto_save_interval(self, interval_str):
        self.auto_save_interval = interval_str
        
        # Check/uncheck the correct QAction
        for action, name in self.auto_save_map.items():
            action.setChecked(name == interval_str)
            
        # Manage QTimer
        if hasattr(self, 'auto_save_timer') and self.auto_save_timer:
            self.auto_save_timer.stop()
        else:
            self.auto_save_timer = QTimer(self)
            self.auto_save_timer.timeout.connect(self.auto_save_trigger)
            
        if interval_str == "immediate":
            pass
        elif interval_str == "1min":
            self.auto_save_timer.start(60000)
        elif interval_str == "5min":
            self.auto_save_timer.start(300000)
        elif interval_str == "15min":
            self.auto_save_timer.start(900000)
        elif interval_str == "disabled":
            pass

        # Setup for heartbeat timer
        if not hasattr(self, 'heartbeat_timer'):
            from Application_Logic.Logic_File_Locking import LOCK_HEARTBEAT_INTERVAL_SECONDS
            self.heartbeat_timer = QTimer(self)
            self.heartbeat_timer.timeout.connect(self.write_lock_heartbeat)
        
        if not self.heartbeat_timer.isActive():
            from Application_Logic.Logic_File_Locking import LOCK_HEARTBEAT_INTERVAL_SECONDS
            self.heartbeat_timer.start(LOCK_HEARTBEAT_INTERVAL_SECONDS * 1000)

    def auto_save_trigger(self):
        if self.current_project_file and getattr(self, 'edit_mode', True):
            if ProjectSaver.has_temp_changes(self.current_project_file):
                self.save_project()

    def show_history_dialog(self):
        if not hasattr(self, 'history_manager') or not self.history_manager:
            from Application_Logic.Logic_History import HistoryManager
            path = self.current_project_file if self.current_project_file else ""
            self.history_manager = HistoryManager(path)
            
        from UI.Dialog_History import HistoryDialog
        dialog = HistoryDialog(self.history_manager.history, self)
        dialog.exec()

    def show_all_baselines_dialog(self):
        from UI.Dialog_Release_Selection import AllBaselinesDialog
        dialog = AllBaselinesDialog(self.arch_controller.release_manager, self.arch_controller, self)
        dialog.exec()

    def enter_test_mode(self):
        if not getattr(self, 'master_password_hash', None):
            QMessageBox.warning(self, "Test Mode", "A master password must be configured on the project to enter Test Mode.")
            return
            
        from Application_Logic.Logic_Security import MasterPasswordPromptDialog, SecurityManager
        prompt = MasterPasswordPromptDialog(self, "Enter Master Password to Enter Test Mode:")
        if prompt.exec():
            entered = prompt.get_password()
            if SecurityManager.verify_password(entered, self.master_password_hash):
                self.test_mode = True
                self.actionEnter_Test_Mode.setVisible(False)
                self.actionExit_Test_Mode.setVisible(True)
                
                # Show in status bar: add red indicator
                if not hasattr(self, 'test_mode_indicator'):
                    self.test_mode_indicator = QtWidgets.QLabel(" TEST MODE ", self)
                    self.test_mode_indicator.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
                    self.ui.statusbar.addPermanentWidget(self.test_mode_indicator)
                self.test_mode_indicator.show()
                self.ui.statusbar.showMessage("Entered Test Mode.")
                
                # Update lock file
                self.update_lock_test_mode(True)
            else:
                QMessageBox.critical(self, "Access Denied", "Incorrect master password.")

    def exit_test_mode(self):
        self.test_mode = False
        self.actionEnter_Test_Mode.setVisible(True)
        self.actionExit_Test_Mode.setVisible(False)
        if hasattr(self, 'test_mode_indicator'):
            self.test_mode_indicator.hide()
        self.ui.statusbar.showMessage("Exited Test Mode.")
        self.update_lock_test_mode(False)

    def update_lock_test_mode(self, active: bool):
        if not self.current_project_file:
            return
        from Application_Logic.Logic_File_Locking import FileLockManager
        lock_file = FileLockManager.get_lock_file_path(self.current_project_file)
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    data = json.load(f)
                if active:
                    data["test_mode"] = True
                else:
                    data.pop("test_mode", None)
                with open(lock_file, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                print(f"Failed to update lock file: {e}")

def apply_adwaita_theme(app):
    """
    Applies a dark theme inspired by GNOME Adwaita.
    """
    app.setStyle("Fusion")
    
    palette = QPalette()
    
    # Adwaita Dark Colors
    window_color = QColor(36, 36, 36)
    window_text_color = QColor(255, 255, 255)
    base_color = QColor(46, 46, 46)
    alternate_base_color = QColor(56, 56, 56)
    tool_tip_base_color = QColor(255, 255, 255)
    tool_tip_text_color = QColor(0, 0, 0)
    text_color = QColor(255, 255, 255)
    button_color = QColor(53, 53, 53)
    button_text_color = QColor(255, 255, 255)
    bright_text_color = QColor(255, 0, 0)
    link_color = QColor(42, 130, 218)
    highlight_color = QColor(53, 132, 228) # Adwaita Blue
    highlighted_text_color = QColor(255, 255, 255)
    
    palette.setColor(QPalette.ColorRole.Window, window_color)
    palette.setColor(QPalette.ColorRole.WindowText, window_text_color)
    palette.setColor(QPalette.ColorRole.Base, base_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, alternate_base_color)
    palette.setColor(QPalette.ColorRole.ToolTipBase, tool_tip_base_color)
    palette.setColor(QPalette.ColorRole.ToolTipText, tool_tip_text_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, button_color)
    palette.setColor(QPalette.ColorRole.ButtonText, button_text_color)
    palette.setColor(QPalette.ColorRole.BrightText, bright_text_color)
    palette.setColor(QPalette.ColorRole.Link, link_color)
    palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, highlighted_text_color)
    
    # Disabled state
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127))

    app.setPalette(palette)
    
    # Optional: Set stylesheet for specific tweaks if needed
    app.setStyleSheet("""
        QToolTip { 
            color: #ffffff; 
            background-color: #2a82da; 
            border: 1px solid white; 
        }
    """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_adwaita_theme(app)
    window = ApplicationWindow()
    window.show()
    sys.exit(app.exec())
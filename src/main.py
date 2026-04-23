import sys
import os

# Optional: Ensure local imports work if running directly from this folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPalette, QColor
import UI
import Application_Logic as App_Logic
from Application_Logic.Logic_Project_Saving import ProjectSaver

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Instantiate the generated UI class
        self.ui = UI.Ui_MainWindow()
        
        # Set up the user interface on this QMainWindow instance
        self.ui.setupUi(self)

        # Initialize the specialized controllers
        self.arch_controller = App_Logic.ArchitectureTabController(self)
        
        #initialize parser storage
        self.parser = None

        #Connect Menu Actions
        self.ui.mnu_New_Project.triggered.connect(self.new_project)
        self.ui.actionSave.triggered.connect(self.save_project)
        self.ui.actionSave_project_as.triggered.connect(self.save_project_as)
        self.ui.mnu_Load_Project.triggered.connect(self.load_project)
        
        # Connect Sidebar Actions
        self.ui.SellectSoftware_Release.clicked.connect(self.handle_select_release)

        # Current Project File
        self.current_project_file = None

        # Trigger "New Project" dialog automatically after the window is shown
        # 100ms is enough to let the UI render first
        QTimer.singleShot(100, self.new_project)

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

        dialog = App_Logic.NewProjectController()

        if dialog.exec():
            # if the user loaded a file, we grab the parser form dialog
            self.parser = dialog.parser
            self.ui.statusbar.showMessage("Project initialized successfully.")

            # Pass the data to the controller
            # dialog.release_name is captured in Logic_New_Project
            self.arch_controller.populate_from_parser(self.parser, release_name=dialog.release_name)
            self.current_project_file = None

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
            
            success, msg = ProjectSaver.save_project(self, file_path)
            self.ui.statusbar.showMessage(msg)
            if success:
                self.current_project_file = file_path
            else:
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
                    event.accept()
                else:
                    QMessageBox.critical(self, "Save Error", f"Could not save project: {msg}")
                    event.ignore()
            
            elif reply == QMessageBox.StandardButton.No:
                # Discard changes -> cleanup temp file
                ProjectSaver.cleanup_temp(self.current_project_file)
                event.accept()
            
            else:
                event.ignore()
        else:
            event.accept()

    def load_project(self):
        # Supports both Directory Projects (Preferred) and Legacy Files
        # We use a custom dialog loop or just try one then the other?
        # Simpler: Try to open Directory. If user Cancels, do nothing. 
        # Add a separate "Load Legacy" action? 
        # Or just use getOpenFileName? It can't open dirs.
        # Let's use getExistingDirectory.
        
        file_path = QFileDialog.getExistingDirectory(self, "Load Project Folder", "")
        
        if not file_path:
            # Fallback for Legacy Files if they didn't pick a folder? 
            # Often users convert, so let's allow them to pick a file if they want.
            # But getExistingDirectory returns "" on cancel.
            # Maybe we ask? 
            # Let's keep it simple: "Open Project Folder".
            # If they really want a legacy file, we can add a "Load Legacy File" feature later or they can name their folder .arch
            pass
        
        if file_path:
            # Issue: Clean up any stale temp files from previous sessions for THIS loaded project
            ProjectSaver.cleanup_temp(file_path)

            success, msg = ProjectSaver.load_project(self, file_path)
            self.ui.statusbar.showMessage(msg)
            if success:
                self.current_project_file = file_path
            else:
                QMessageBox.critical(self, "Load Error", msg)

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
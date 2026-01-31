import sys
import os

# Optional: Ensure local imports work if running directly from this folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer
import UI
import Application_Logic as App_Logic

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

        # Trigger "New Project" dialog automatically after the window is shown
        # 100ms is enough to let the UI render first
        QTimer.singleShot(100, self.new_project)

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
            self.arch_controller.populate_from_parser(self.parser)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ApplicationWindow()
    window.show()
    sys.exit(app.exec())
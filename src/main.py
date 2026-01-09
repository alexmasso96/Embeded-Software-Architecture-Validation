import sys
import os

# Optional: Ensure local imports work if running directly from this folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow
import UI
import Application_Logic as App_Logic

class ApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Instantiate the generated UI class
        self.ui = UI.Ui_MainWindow()
        
        # Set up the user interface on this QMainWindow instance
        self.ui.setupUi(self)
        
        #initialize parser storage
        self.parser = None

        #Connect Menu Actions
        self.ui.mnu_New_Project.triggered.connect(self.new_project)

    def new_project(self):
        """
        Handler for the 'New Project' menu item
        """

        dialog = App_Logic.NewProjectController()

        if dialog.exec():
            # if the user loaded a file, we grab the parser form dialog
            self.parser = dialog.parser
            self.ui.statusbar.showMessage("Project initialized successfully.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ApplicationWindow()
    window.show()
    sys.exit(app.exec())
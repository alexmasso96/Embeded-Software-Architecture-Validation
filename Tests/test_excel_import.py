import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from Tests.test_helpers import make_project_db
import openpyxl

def test_import_flow():
    with tempfile.TemporaryDirectory() as tmp:
        # Create Excel fixture
        excel_path = os.path.join(tmp, "test_import.xlsx")
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Architecture_1"
        # 4 Excel rows; the controller inserts 1 placeholder row on init before
        # flush runs, so arch1 ends up with 1 + 4 = 5 rows total.
        ws1.append(["Port Name"])
        ws1.append(["port_a"])
        ws1.append(["port_b"])
        ws1.append(["port_c"])

        ws2 = wb.create_sheet(title="Architecture_2")
        # 4 Excel rows; arch2 has no pre-existing placeholder, so it ends up
        # with exactly 4 rows.
        ws2.append(["Port Name"])
        ws2.append(["port_x"])
        ws2.append(["port_y"])
        ws2.append(["port_z"])
        wb.save(excel_path)
        
        # Create DB project fixture
        proj_path = os.path.join(tmp, "test_import.arch")
        layout = [("PortSearchColumn", "Port", True)]
        models = [
            {"name": "Architecture_1", "status": "In Work", "rows": []},
            {"name": "Architecture_2", "status": "In Work", "rows": []}
        ]
        db = make_project_db(proj_path, layout=layout, models=models)
        
        mgr = ArchitectureManager()
        mgr.set_db(db)
        
        window = QMainWindow()
        window.ui = UI.Ui_MainWindow()
        window.ui.setupUi(window)
        window.current_project_file = proj_path
        
        controller = ArchitectureTabController(window)
        controller.model_manager = mgr
        window.arch_controller = controller
        window.project_db = db  # prevent save_project from recreating the DB and reloading mgr.models

        mock_file_dialog = MagicMock(return_value=(excel_path, "Excel Files (*.xlsx)"))
        
        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', mock_file_dialog), \
             patch('Application_Logic.Logic_Architecture_Import.ImportModeDialog') as MockModeDialog, \
             patch('Application_Logic.Logic_Architecture_Import.ImportConfirmationDialog') as MockConfirmDialog, \
             patch('PyQt6.QtWidgets.QMessageBox.information'), \
             patch('PyQt6.QtWidgets.QMessageBox.warning'):

            mode_instance = MagicMock()
            mode_instance.exec.return_value = True
            mode_instance.selected_mode = "automated"
            MockModeDialog.return_value = mode_instance

            confirm_instance = MagicMock()
            confirm_instance.exec.return_value = True
            confirm_instance.selected_action = "confirm"
            MockConfirmDialog.return_value = confirm_instance

            controller.import_architecture_excel()
            
            # Verify data
            arch1 = next(m for m in mgr.models if m.name == "Architecture_1")
            assert len(arch1.data_cache.get("rows", [])) == 5

            arch2 = next(m for m in mgr.models if m.name == "Architecture_2")
            assert len((arch2.data_cache or {}).get("rows", [])) == 4

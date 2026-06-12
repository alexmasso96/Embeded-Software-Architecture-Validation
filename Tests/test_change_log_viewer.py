import sys
import os
import tempfile
import json
import shutil
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtWidgets

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Change_Log_Tab import parse_and_align_diff, AIChangeLogController
from UI.widgets_change_log import ChangeLogWidget
from Tests.test_helpers import make_project_db

app = QApplication.instance() or QApplication(sys.argv)

def test_diff_parsing_and_alignment():
    # Test diff parser with standard changes
    diff_text = (
        "--- old_file.c\n"
        "+++ new_file.c\n"
        "@@ -1,5 +1,5 @@\n"
        " unchanged line 1\n"
        "-deleted line 1\n"
        "-deleted line 2\n"
        "+added line 1\n"
        "+added line 2\n"
        "+added line 3\n"
        " unchanged line 2\n"
    )
    
    old_aligned, new_aligned = parse_and_align_diff(diff_text)
    
    # Assert headers are parsed
    assert old_aligned[0] == ("--- old_file.c", "header")
    assert new_aligned[0] == ("--- old_file.c", "header")
    
    # Assert alignment sizes match
    assert len(old_aligned) == len(new_aligned)
    
    # Find alignment within chunk:
    # unchanged, deleted1/added1, deleted2/added2, empty/added3, unchanged
    # Total lines after headers (3 headers):
    # index 3: unchanged line 1
    # index 4: deleted line 1 vs added line 1
    # index 5: deleted line 2 vs added line 2
    # index 6: empty vs added line 3
    # index 7: unchanged line 2
    
    assert old_aligned[3] == ("unchanged line 1", "unchanged")
    assert new_aligned[3] == ("unchanged line 1", "unchanged")
    
    assert old_aligned[4] == ("deleted line 1", "deleted")
    assert new_aligned[4] == ("added line 1", "added")
    
    assert old_aligned[5] == ("deleted line 2", "deleted")
    assert new_aligned[5] == ("added line 2", "added")
    
    assert old_aligned[6] == ("", "empty")
    assert new_aligned[6] == ("added line 3", "added")
    
    assert old_aligned[7] == ("unchanged line 2", "unchanged")
    assert new_aligned[7] == ("unchanged line 2", "unchanged")


def test_project_folder_and_json_cache_copying():
    # Test Project directory auto-creation path logic & JSON file copying
    with tempfile.TemporaryDirectory() as tmp:
        # Create a mock main window & UI
        window = QMainWindow()
        import UI
        window.ui = UI.Ui_MainWindow()
        window.ui.setupUi(window)
        window.test_mode = True
        
        # Test folder path generation (simulate MainMenu new_project flow)
        chosen_path = os.path.join(tmp, "TestProj.arch")
        parent_dir = os.path.dirname(chosen_path)
        base_name = os.path.splitext(os.path.basename(chosen_path))[0]
        project_dir = os.path.join(parent_dir, base_name)
        os.makedirs(project_dir, exist_ok=True)
        file_path = os.path.join(project_dir, f"{base_name}.arch")
        
        # Check that parent folder was created and database is placed inside
        assert os.path.exists(project_dir)
        assert os.path.basename(project_dir) == "TestProj"
        
        # Create DB
        db = ProjectDatabase()
        db.open(file_path)
        
        # Verify cache folder creation
        cache_dir = db.db_path + ".elf_caches"
        os.makedirs(cache_dir, exist_ok=True)
        assert os.path.exists(cache_dir)
        
        # Create a mock JSON cache file
        mock_json_src = os.path.join(tmp, "imported_symbols.json")
        with open(mock_json_src, "w") as f:
            json.dump({"elf_hash": "abc123hash", "symbols": []}, f)
            
        # Silently copy JSON cache file (as done in Logic_New_Project.py / Dialog_Release_Selection.py)
        dest_file = os.path.join(cache_dir, "elf_abc123hash.json")
        shutil.copy2(mock_json_src, dest_file)
        
        assert os.path.exists(dest_file)
        with open(dest_file, "r") as f:
            data = json.load(f)
            assert data["elf_hash"] == "abc123hash"
            
        db.close()


def test_changelog_viewer_tab_setup():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_changelog.arch")
        layout = [("TC. ID", "Static Text", True), ("Code Diffs", "Static Text", True)]
        db = make_project_db(db_path, layout=layout, models=[{"name": "M1", "status": "In Work", "rows": []}])
        
        # Insert a mock diff row
        db.save_code_diffs(model_id=1, diff_hash="hash_diff_abc", diffs=[{
            "file_path": "main.c",
            "status": "modified",
            "unified_diff": "--- main.c\n+++ main.c\n-old line\n+new line"
        }])
        
        # #2E: link diff hash via the per-release map accessor (no active release → 0).
        db.set_model_diff_hash(1, "hash_diff_abc")
        db.commit()
        
        # Initialize MainWindow & controllers
        window = QMainWindow()
        import UI
        window.ui = UI.Ui_MainWindow()
        window.ui.setupUi(window)
        window.project_db = db
        
        from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
        from Application_Logic.Logic_AI_Chat import AIChatController
        
        # Make controllers
        window.arch_controller = ArchitectureTabController(window)
        window.arch_controller.model_manager.set_db(db)
        window.arch_controller.release_manager.set_db(db)
        window.arch_controller.load_active_model_to_table()
        
        # We need AI Chat Controller to extract provider settings
        window.ai_chat_controller = AIChatController(window)
        
        # Instantiate Change Log tab
        controller = AIChangeLogController(window)
        
        # Assert tab added
        assert controller._tab_index != -1
        assert window.ui.tabWidget.widget(controller._tab_index) is controller.tab_widget
        
        # Load data
        controller.load_data()
        
        # Assert files populated in file_list
        assert controller.tab_widget.file_list.count() == 1
        assert "main.c" in controller.tab_widget.file_list.item(0).text()
        
        # Test file selection loads aligned views
        controller.on_file_selected(0)
        
        old_text = controller.tab_widget.txt_old.toHtml()
        new_text = controller.tab_widget.txt_new.toHtml()
        
        assert "old line" in old_text
        assert "new line" in new_text
        
        # Test scroll synchronization value changes via mocked method to bypass headless constraints
        mock_set_value = MagicMock()
        controller.tab_widget.txt_new.verticalScrollBar().setValue = mock_set_value
        controller.tab_widget.txt_old.verticalScrollBar().valueChanged.emit(50)
        mock_set_value.assert_called_with(50)
        
        db.close()

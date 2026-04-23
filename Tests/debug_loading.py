import sys
import os
import shutil
import json
from dataclasses import asdict

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Architecture_Models import ArchitectureManager, ArchitectureModel
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController

# Mock for MainWindow/UI
class MockUI:
    def __init__(self):
        self.listView = None 
        self.Architecture_Table = None

class MockMainWindow:
    def __init__(self):
        self.ui = MockUI()
        self.parser = None
        self.current_project_file = None

def reproduce_issue():
    print("Starting Reproduction...")
    test_dir = "test_debug_project"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    # 1. Setup Manager
    mgr = ArchitectureManager(test_dir)
    
    # Model 1 (Default) - Index 0
    m1 = mgr.models[0]
    m1.name = "Model A"
    m1_file = m1.file_path
    with open(m1_file, 'w') as f:
        json.dump({"rows": [{"TC. ID": {"text": "Row1_A"}}]}, f)
        
    # Model 2 (Visible) - Index 1
    m2 = mgr.create_model("Model B", "In Work")
    m2_file = m2.file_path
    with open(m2_file, 'w') as f:
        json.dump({"rows": [{"TC. ID": {"text": "Row1_B"}}]}, f)

    # Model 3 (Deleted) - Index 2
    m3 = mgr.create_model("Model C", "Retired")
    m3_file = m3.file_path
    with open(m3_file, 'w') as f:
        json.dump({"rows": [{"TC. ID": {"text": "Row1_C"}}]}, f)
    
    mgr.soft_delete_model(2) # Delete Model C
    
    mgr.save_registry()
    print("Setup Complete. Registry Saved.")
    
    # 2. Simulate Load
    print("\nSimulating Load...")
    
    # Create new Controller/Manager pair (like reloading App)
    mock_main = MockMainWindow()
    # We can't easily instantiate Controller because it needs UI elements.
    # But we can test Manager loading isolation logic.
    
    mgr2 = ArchitectureManager(None) 
    # Logic_Project_Saving flow:
    # 1. set_project_path
    mgr2.set_project_path(test_dir)
    # 2. load_registry
    mgr2.load_registry()
    
    print(f"Loaded {len(mgr2.models)} models.")
    for i, m in enumerate(mgr2.models):
        print(f"[{i}] {m.name} (Deleted: {m.is_deleted}) Path: {m.file_path}")
        
    # Verify Model B (Index 1) File Loading
    model_b = mgr2.models[1]
    if os.path.exists(model_b.file_path):
        with open(model_b.file_path, 'r') as f:
            data = json.load(f)
            print(f"Model B Data on Disk: {data}")
            if not data.get("rows"):
                print("FAILURE: Model B empty on disk!")
            else:
                 if data["rows"][0]["TC. ID"]["text"] == "Row1_B":
                     print("SUCCESS: Model B data intact on disk.")
                 else:
                     print("FAILURE: Model B data mismatch.")
    else:
        print(f"FAILURE: Model B file missing: {model_b.file_path}")

    # Verify Active Retrieval Check
    # Simulate user clicking Index 1 (if C is deleted, B is visual 1? No.)
    # Visual list: [Model A, Model B].
    # Click Row 1 -> Should be Model B.
    
    # Let's instantiate ListModel to verify index mapping
    from Application_Logic.Logic_Architecture_Models import ArchitectureListModel
    list_model = ArchitectureListModel(mgr2)
    
    print("\nChecking Index Mapping:")
    for visual_row in range(list_model.rowCount()):
        real_idx = list_model.get_real_index(visual_row)
        m = mgr2.models[real_idx]
        print(f"Visual {visual_row} -> Real {real_idx} -> {m.name}")
        
    # Clean up
    # shutil.rmtree(test_dir)

if __name__ == "__main__":
    reproduce_issue()

import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Architecture_Models import ArchitectureManager, ArchitectureModel
# Smoke test UI imports (will fail if syntax error)
from UI.Dialog_Architecture_Manager import ArchitectureManagerDialog
from UI.Dialog_Architecture_Edit import ArchitectureEditDialog

def verify_logic():
    print("Starting Logic Verification...")
    
    # Setup Test Dir
    test_dir = "test_arch_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    # 1. Init Manager with Path
    mgr = ArchitectureManager(test_dir)
    assert len(mgr.models) == 1
    assert mgr.models[0].name == "Architecture_1"
    print("Test 1: Initialization Passed")
    
    # 2. CRUD
    # Create
    m2 = mgr.create_model("Model B", "In Work")
    assert len(mgr.models) == 2
    assert m2.name == "Model B"
    assert os.path.exists(m2.file_path)
    print("Test 2: Creation Passed")
    
    # Duplicate
    m2_dup = mgr.create_model("Model B Copy", "Released", copy_from_index=1)
    assert len(mgr.models) == 3
    assert m2_dup.name == "Model B Copy"
    assert m2_dup.status == "Released"
    print("Test 3: Duplication Passed")
    
    # Delete (Soft)
    mgr.soft_delete_model(0) # Delete Default
    assert mgr.models[0].is_deleted is True
    assert len(mgr.get_visible_models()) == 2
    print("Test 4: Soft Delete Passed")
    
    # Restore
    mgr.restore_model(0)
    assert mgr.models[0].is_deleted is False
    assert len(mgr.get_visible_models()) == 3
    print("Test 5: Restore Passed")
    
    # Move
    # List is [Default, Model B, Copy]
    # Move Copy (2) to 0
    mgr.move_model(2, 0)
    # List should be [Copy, Default, Model B]
    assert mgr.models[0].name == "Model B Copy"
    print("Test 6: Move Passed")
    
    # Persistence
    mgr.save_registry()
    
    # Reload
    mgr2 = ArchitectureManager(test_dir)
    assert len(mgr2.models) == 3
    assert mgr2.models[0].name == "Model B Copy"
    print("Test 7: Persistence Passed")
    
    # Clean up
    shutil.rmtree(test_dir)
    print("\nALL VERIFICATION STEPS PASSED")

if __name__ == "__main__":
    verify_logic()

import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager, ReleaseModel

def test_baseline_features():
    print("Starting Baseline Features Unit Test...")
    
    # Setup Test Dir
    test_dir = "test_baseline_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    try:
        # 1. Initialize ReleaseManager
        mgr = ReleaseManager(test_dir)
        
        # 2. Create a normal release
        rel = mgr.create_release("Release_1.0", "First Release", copy_from_active=False)
        assert len(mgr.releases) == 1
        assert mgr.releases[0].name == "Release_1.0"
        assert not mgr.releases[0].is_baseline
        print("Test 1: Normal release creation passed.")
        
        # Add some sample data to release data cache
        sample_data = {
            "rows": [
                {"TC. ID": {"text": "TC_001"}, "Input Port": {"text": "PortA"}}
            ]
        }
        mgr._save_data(rel, sample_data)
        
        # 3. Create a baseline
        layout_data = {
            "version": "2.0",
            "layout": [["TC. ID", "Static Text", True]],
            "settings": {"default_cyclicity": "10"}
        }
        
        baseline_name = "My_Custom_Baseline"
        baseline = mgr.create_baseline(0, baseline_name, layout_data, active_model_data=sample_data)
        
        # Check in-memory state
        assert len(mgr.releases) == 2
        # baselines are appended to the list
        assert mgr.releases[1].name == "My_Custom_Baseline"
        assert mgr.releases[1].is_baseline
        assert mgr.releases[1].parent_release_name == "Release_1.0"
        print("Test 2: Baseline creation in registry passed.")
        
        # Check files on disk
        baseline_dir = os.path.join(test_dir, "Baselines", baseline_name)
        assert os.path.isdir(baseline_dir)
        
        table_data_path = os.path.join(baseline_dir, "table_data.json")
        layout_path = os.path.join(baseline_dir, "layout.json")
        metrics_path = os.path.join(baseline_dir, "metrics.json")
        
        assert os.path.isfile(table_data_path)
        assert os.path.isfile(layout_path)
        assert os.path.isfile(metrics_path)
        print("Test 3: Baseline files created on disk.")
        
        # Validate table data contents
        with open(table_data_path, 'r') as f:
            loaded_table = json.load(f)
        assert loaded_table["rows"][0]["TC. ID"]["text"] == "TC_001"
        
        # Validate layout contents
        with open(layout_path, 'r') as f:
            loaded_layout = json.load(f)
        assert loaded_layout["settings"]["default_cyclicity"] == "10"
        print("Test 4: Saved contents are correct.")
        
        # 4. Inhibit release deletion when baseline exists
        # In this list, releases[0] is Release_1.0 (since it was inserted at 0), releases[1] is baseline
        # Let's find index of Release_1.0
        rel_idx = mgr.releases.index(rel)
        delete_result = mgr.delete_release(rel_idx)
        # Should return a tuple (False, "Cannot delete release that has baselines.")
        assert isinstance(delete_result, tuple)
        assert delete_result[0] is False
        print("Test 5: Block release deletion with baseline passed.")
        
        # 5. Clean up baseline folder when baseline is deleted (should preserve folder for soft deletion)
        baseline_idx = mgr.releases.index(baseline)
        delete_baseline_result = mgr.delete_release(baseline_idx)
        assert delete_baseline_result is True or (isinstance(delete_baseline_result, tuple) and delete_baseline_result[0] is True)
        
        # Check baseline folder is preserved (soft-deleted)
        assert os.path.exists(baseline_dir)
        assert mgr.releases[baseline_idx].is_deleted is True
        print("Test 6: Baseline folder preservation on soft-delete passed.")
        
        # 6. Release deletion can now succeed
        rel_idx = mgr.releases.index(rel)
        delete_rel_result = mgr.delete_release(rel_idx)
        assert delete_rel_result is True or (isinstance(delete_rel_result, tuple) and delete_rel_result[0] is True)
        # Release is popped, but soft-deleted baseline remains in registry
        assert len(mgr.releases) == 1
        assert mgr.releases[0].is_baseline and mgr.releases[0].is_deleted
        print("Test 7: Release deletion post-baseline removal passed.")
        
        print("\nALL BASELINE FEATURE UNIT TESTS PASSED!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_baseline_features()

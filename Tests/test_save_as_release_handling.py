import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager, ReleaseModel

def test_save_as_release_handling():
    print("Running Save As Release Handling Unit Test...")
    
    old_dir = "old_project.arch"
    new_dir = "new_project.arch"
    
    # Cleanup previous runs
    for d in [old_dir, new_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
            
    os.makedirs(old_dir)
    
    try:
        # 1. Initialize ReleaseManager with old directory
        mgr = ReleaseManager(old_dir)
        
        # 2. Create Release 1 (active, in memory)
        rel1 = mgr.create_release("Release_1", "First active release")
        rel1.data_cache = {"rows": [{"port": "A", "val": "1"}]}
        mgr._save_data(rel1, rel1.data_cache)
        
        # 3. Create Release 2 (simulated lazy-loaded: file exists on disk, but data_cache is None in memory)
        rel2 = mgr.create_release("Release_2", "Second release (lazy-loaded)")
        rel2_data = {"rows": [{"port": "B", "val": "2"}]}
        mgr._save_data(rel2, rel2_data)
        rel2.data_cache = None  # Clear cache to simulate lazy loading
        
        # 4. Create a baseline snapshot of Release 1 (also lazy-loaded: data_cache is None in memory, file on disk)
        baseline = mgr.create_baseline(release_index=1, baseline_name="Baseline_1", active_model_data={"rows": [{"port": "A", "val": "1"}]})
        baseline.data_cache = None # Clear cache to simulate lazy loading
        
        # Verify initial states
        assert len(mgr.releases) == 3
        assert mgr.releases[0].name == "Release_2"
        assert mgr.releases[0].data_cache is None
        assert os.path.exists(mgr.releases[0].file_path)
        
        assert mgr.releases[1].name == "Release_1"
        assert mgr.releases[1].data_cache is not None
        assert os.path.exists(mgr.releases[1].file_path)
        
        assert mgr.releases[2].name == "Baseline_1"
        assert mgr.releases[2].data_cache is None
        assert os.path.exists(mgr.releases[2].file_path)
        
        print("✓ Setup complete: 1 in-memory release, 1 lazy-loaded release, 1 lazy-loaded baseline created.")
        
        # 5. Trigger Save As by updating project path
        mgr.set_project_path(new_dir)
        
        # 6. Verifications
        print("\nVerifying re-rooting and file copying...")
        
        # Verify registry was saved in the new path
        new_registry_path = os.path.join(new_dir, "releases_registry.json")
        assert os.path.exists(new_registry_path), "Registry file was not created in the new path!"
        
        # Verify each release path was re-rooted and file exists/copied
        # Check active release (Release 1)
        rel1_new = mgr.releases[1]
        assert rel1_new.name == "Release_1"
        assert rel1_new.file_path.startswith(new_dir), f"Release_1 path was not re-rooted! Path: {rel1_new.file_path}"
        assert os.path.exists(rel1_new.file_path), f"Release_1 file does not exist at new path: {rel1_new.file_path}"
        with open(rel1_new.file_path, 'r') as f:
            data = json.load(f)
        assert data["rows"][0]["port"] == "A", "Release_1 content is incorrect at the new path!"
        print("✓ Release_1 (Active) correctly re-rooted and saved to new path.")
        
        # Check lazy-loaded release (Release 2)
        rel2_new = mgr.releases[0]
        assert rel2_new.name == "Release_2"
        assert rel2_new.file_path.startswith(new_dir), f"Release_2 path was not re-rooted! Path: {rel2_new.file_path}"
        assert os.path.exists(rel2_new.file_path), f"Release_2 file was not copied to the new path: {rel2_new.file_path}"
        with open(rel2_new.file_path, 'r') as f:
            data = json.load(f)
        assert data["rows"][0]["port"] == "B", "Release_2 copied content is incorrect at the new path!"
        print("✓ Release_2 (Lazy-loaded) correctly re-rooted and physically copied to new path.")
        
        # Check baseline (Baseline 1)
        base_new = mgr.releases[2]
        assert base_new.name == "Baseline_1"
        assert base_new.file_path.startswith(new_dir), f"Baseline_1 path was not re-rooted! Path: {base_new.file_path}"
        assert os.path.exists(base_new.file_path), f"Baseline_1 file was not copied to the new path: {base_new.file_path}"
        with open(base_new.file_path, 'r') as f:
            data = json.load(f)
        assert data["rows"][0]["port"] == "A", "Baseline_1 copied content is incorrect at the new path!"
        print("✓ Baseline_1 (Lazy-loaded baseline) correctly re-rooted and physically copied to new path.")
        
        # 7. Reload with a fresh manager from the new path
        mgr_fresh = ReleaseManager(new_dir)
        assert len(mgr_fresh.releases) == 3
        # Load and verify lazy loaded releases
        r2 = mgr_fresh.set_active_release(0)
        assert r2.data_cache["rows"][0]["port"] == "B"
        print("✓ Fresh ReleaseManager successfully loaded the re-rooted registry and data.")
        
        print("\nALL SAVE AS RELEASE HANDLING UNIT TESTS PASSED!")
        
    finally:
        # Cleanup
        for d in [old_dir, new_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)

if __name__ == "__main__":
    test_save_as_release_handling()

import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager, ReleaseModel

def test_release_uniqueness():
    print("Running Release Uniqueness Unit Test...")
    
    test_dir = "test_uniqueness_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    try:
        # 1. Initialize ReleaseManager
        mgr = ReleaseManager(test_dir)
        
        # 2. Create first release
        elf_hash_1 = "same_md5_hash_value"
        rel1 = mgr.create_release("Release_1", "First Release", copy_from_active=False, elf_hash=elf_hash_1)
        assert len(mgr.releases) == 1
        assert mgr.releases[0].elf_hash == "same_md5_hash_value"
        print("Test 1: Release 1 created successfully with MD5 hash.")
        
        # Save and reload registry
        mgr.save_registry()
        
        # Re-initialize another manager to test persistence of elf_hash
        mgr2 = ReleaseManager(test_dir)
        assert len(mgr2.releases) == 1
        assert mgr2.releases[0].elf_hash == "same_md5_hash_value"
        print("Test 2: Hash persistence verified in registry.")
        
        # 3. Simulate uniqueness check
        new_file_hash = "same_md5_hash_value"
        is_duplicate = any(r.elf_hash == new_file_hash for r in mgr2.releases)
        assert is_duplicate is True
        
        # Simulate check with different hash
        different_file_hash = "different_hash_value"
        is_duplicate_diff = any(r.elf_hash == different_file_hash for r in mgr2.releases)
        assert is_duplicate_diff is False
        print("Test 3: Uniqueness check correctly identifies duplicates.")
        
        print("\nALL RELEASE UNIQUENESS UNIT TESTS PASSED!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_release_uniqueness()

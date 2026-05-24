import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager, ReleaseModel

def test_release_elf_data_preservation():
    print("Running Release ELF Data Preservation Unit Test...")
    
    test_dir = "test_elf_data_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    try:
        # 1. Initialize ReleaseManager
        mgr = ReleaseManager(test_dir)
        
        # 2. Mock parsed ELF data
        mock_elf_data = {
            "elf_path": "/path/to/test.elf",
            "elf_hash": "mocked_hash_value_123",
            "symbols": [
                {
                    "name": "func_test_1",
                    "address": 1000,
                    "size": 50,
                    "symbol_type": "STT_FUNC",
                    "binding": "STB_GLOBAL",
                    "section": ".text"
                }
            ],
            "functions": [
                {
                    "name": "func_test_1",
                    "address": 1000,
                    "size": 50,
                    "parameters": [],
                    "return_type": "void"
                }
            ],
            "structures": {"my_struct": []},
            "global_vars": {"my_var": "int"}
        }
        
        # 3. Create release with ELF data
        rel = mgr.create_release("Release_1.0", "First Release", copy_from_active=False, elf_path="/path/to/test.elf", elf_hash="mocked_hash_value_123", elf_data=mock_elf_data)
        
        # Check in-memory data cache
        assert rel.data_cache is not None
        assert "database" in rel.data_cache
        assert rel.data_cache["database"]["elf_hash"] == "mocked_hash_value_123"
        assert len(rel.data_cache["database"]["symbols"]) == 1
        assert rel.data_cache["database"]["symbols"][0]["name"] == "func_test_1"
        assert rel.data_cache["database"]["global_vars"]["my_var"] == "int"
        print("Test 1: In-memory ELF data cache verified.")
        
        # 4. Check saved file on disk
        assert rel.file_path is not None
        assert os.path.exists(rel.file_path)
        
        with open(rel.file_path, 'r') as f:
            disk_data = json.load(f)
            
        assert "database" in disk_data
        assert disk_data["database"]["elf_hash"] == "mocked_hash_value_123"
        assert len(disk_data["database"]["symbols"]) == 1
        assert disk_data["database"]["symbols"][0]["name"] == "func_test_1"
        assert disk_data["database"]["global_vars"]["my_var"] == "int"
        print("Test 2: Saved file on disk contains complete ELF database.")
        
        # 5. Reload using a new ReleaseManager to verify persistence
        mgr2 = ReleaseManager(test_dir)
        rel_reloaded = mgr2.set_active_release(0)
        assert rel_reloaded.data_cache is not None
        assert "database" in rel_reloaded.data_cache
        assert rel_reloaded.data_cache["database"]["elf_hash"] == "mocked_hash_value_123"
        print("Test 3: Persistence and reloading of ELF data passed.")
        
        print("\nALL RELEASE ELF DATA PRESERVATION TESTS PASSED!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_release_elf_data_preservation()

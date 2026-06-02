import sys
import os
import tempfile

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase


def test_release_elf_data_preservation():
    print("Running Release ELF Data Preservation Unit Test...")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_elf_data.arch")
        db = ProjectDatabase()
        db.open(db_path)
        mgr = ReleaseManager()
        mgr.set_db(db)

        ELF_HASH = "mocked_hash_value_123"
        ELF_PATH = "/path/to/test.elf"

        mock_symbols = [{
            "name": "func_test_1",
            "address": 1000,
            "size": 50,
            "symbol_type": "STT_FUNC",
            "binding": "STB_GLOBAL",
            "section": ".text"
        }]
        mock_functions = [{
            "name": "func_test_1",
            "address": 1000,
            "size": 50,
            "parameters": [],
            "return_type": "void"
        }]
        mock_structures = {"my_struct": []}
        mock_global_vars = {"my_var": "int"}

        # 1. Create release with ELF metadata
        rel = mgr.create_release(
            "Release_1.0", "First Release",
            copy_from_active=False,
            elf_path=ELF_PATH,
            elf_hash=ELF_HASH
        )
        assert rel.elf_hash == ELF_HASH
        assert rel.elf_path == ELF_PATH
        print("Test 1: Release created with ELF metadata.")

        # 2. Store ELF data in DB (simulating what flush_to_db / _populate_parser does)
        db.register_elf(ELF_HASH, ELF_PATH)
        db.bulk_insert_symbols(ELF_HASH, mock_symbols)
        db.bulk_insert_functions(ELF_HASH, mock_functions)
        db.bulk_insert_structures(ELF_HASH, mock_structures)
        db.bulk_insert_global_vars(ELF_HASH, mock_global_vars)
        db.commit()

        assert db.has_elf(ELF_HASH)
        print("Test 2: ELF data stored in DB tables.")

        # 3. Retrieve function names and check
        func_names = db.get_function_names(ELF_HASH)
        assert "func_test_1" in func_names
        print("Test 3: Function names retrievable from DB.")

        # 4. Reload via fresh DB and manager
        db.close()
        db2 = ProjectDatabase()
        db2.open(db_path)
        mgr2 = ReleaseManager()
        mgr2.set_db(db2)

        rel_reloaded = mgr2.set_active_release(0)
        assert rel_reloaded is not None
        assert rel_reloaded.elf_hash == ELF_HASH
        assert db2.has_elf(ELF_HASH)

        func_names2 = db2.get_function_names(ELF_HASH)
        assert "func_test_1" in func_names2
        print("Test 4: ELF data persistence verified after reload.")

        db2.close()
        print("\nALL RELEASE ELF DATA PRESERVATION TESTS PASSED!")


if __name__ == "__main__":
    test_release_elf_data_preservation()

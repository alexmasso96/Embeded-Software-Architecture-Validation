import sys
import os
import json
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.append(os.path.abspath("src"))

from core.elf_parser import ELFParser, Symbol, Function


def test_elf_parser_cache_loading():
    print("Running ELF Parser Cache Loading Test...")

    with tempfile.TemporaryDirectory() as test_dir:
        flat_path = os.path.join(test_dir, "flat_database.json")
        nested_path = os.path.join(test_dir, "nested_database.json")

        elf_data = {
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
            "structures": {},
            "global_vars": {}
        }

        # Write Flat Format Cache
        with open(flat_path, 'w') as f:
            json.dump(elf_data, f)

        # Write Nested Baseline Format Cache (legacy — still supported by load_cache)
        nested_data = {
            "rows": [],
            "column_metadata": {},
            "release_results": {},
            "database": elf_data
        }
        with open(nested_path, 'w') as f:
            json.dump(nested_data, f)

        # Test 1: flat format
        parser_flat = ELFParser()
        assert parser_flat.load_cache(flat_path) is True
        assert parser_flat.md5_hash == "mocked_hash_value_123"
        assert len(parser_flat.symbols) == 1
        assert parser_flat.symbols[0].name == "func_test_1"
        assert len(parser_flat.functions) == 1
        assert parser_flat.functions[0].name == "func_test_1"
        print("Test 1: Flat format cache loading passed.")

        # Test 2: nested baseline format
        parser_nested = ELFParser()
        assert parser_nested.load_cache(nested_path) is True
        assert parser_nested.md5_hash == "mocked_hash_value_123"
        assert len(parser_nested.symbols) == 1
        assert parser_nested.symbols[0].name == "func_test_1"
        assert len(parser_nested.functions) == 1
        assert parser_nested.functions[0].name == "func_test_1"
        print("Test 2: Nested baseline format cache loading passed.")

        # Test 3: DB import from flat cache JSON
        from Application_Logic.Logic_Database import ProjectDatabase
        db_path = os.path.join(test_dir, "test_import.arch")
        db = ProjectDatabase()
        db.open(db_path)
        imported_hash = ELFParser.import_elf_cache_to_db(flat_path, db)
        assert imported_hash == "mocked_hash_value_123"
        assert db.has_elf(imported_hash)
        func_names = db.get_function_names(imported_hash)
        assert "func_test_1" in func_names
        db.close()
        print("Test 3: import_elf_cache_to_db inserts ELF data into SQLite.")

        print("\nALL ELF PARSER CACHE LOADING TESTS PASSED!")


if __name__ == "__main__":
    test_elf_parser_cache_loading()

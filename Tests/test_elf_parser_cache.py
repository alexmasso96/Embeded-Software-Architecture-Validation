import sys
import os
import json
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.append(os.path.abspath("src"))

from core.elf_parser import ELFParser, Symbol, Function

def test_elf_parser_cache_loading():
    print("Running ELF Parser Cache Loading Test...")
    
    test_dir = "test_parser_cache_temp"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    flat_path = os.path.join(test_dir, "flat_database.json")
    nested_path = os.path.join(test_dir, "nested_database.json")
    
    # 1. Mock ELF data
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
    
    # 2. Write Flat Format Cache
    with open(flat_path, 'w') as f:
        json.dump(elf_data, f)
        
    # 3. Write Nested Baseline Format Cache
    nested_data = {
        "rows": [],
        "column_metadata": {},
        "release_results": {},
        "database": elf_data
    }
    with open(nested_path, 'w') as f:
        json.dump(nested_data, f)
        
    try:
        # Test loading flat format
        parser_flat = ELFParser()
        assert parser_flat.load_cache(flat_path) is True
        assert parser_flat.md5_hash == "mocked_hash_value_123"
        assert len(parser_flat.symbols) == 1
        assert parser_flat.symbols[0].name == "func_test_1"
        assert len(parser_flat.functions) == 1
        assert parser_flat.functions[0].name == "func_test_1"
        print("Test 1: Flat format cache loading passed.")
        
        # Test loading nested baseline format
        parser_nested = ELFParser()
        assert parser_nested.load_cache(nested_path) is True
        assert parser_nested.md5_hash == "mocked_hash_value_123"
        assert len(parser_nested.symbols) == 1
        assert parser_nested.symbols[0].name == "func_test_1"
        assert len(parser_nested.functions) == 1
        assert parser_nested.functions[0].name == "func_test_1"
        print("Test 2: Nested baseline format cache loading passed.")
        
        print("\nALL ELF PARSER CACHE LOADING TESTS PASSED!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_elf_parser_cache_loading()

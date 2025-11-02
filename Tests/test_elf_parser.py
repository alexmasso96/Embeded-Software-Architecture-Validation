"""
Test suite for ELF Parser module.
Tests the functionality without requiring an actual ELF file.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.elf_parser import ELFParser, Symbol, Function


def test_with_real_elf():
    """
    Test with a real ELF file if provided.
    Usage: python test_elf_parser.py <path_to_elf_file>
    """
    print("=" * 70)
    print("ELF PARSER TEST SUITE")
    print("=" * 70)
    print("\n Please provide the path to the ELF File")
    elf_path = input()
    if elf_path == "":
        print("\nNo ELF file provided for testing.")
        print("\nTo test with a real ELF file, run:")
        print("  python test_elf_parser.py <path_to_elf_file>")
        print("\nExample:")
        print("  python test_elf_parser.py C:\\path\\to\\firmware.elf")
        print("\n" + "="*70)
        return

    """
    if len(sys.argv) < 2:
        print("="*70)
        print("ELF PARSER TEST SUITE")
        print("="*70)
        print("\nNo ELF file provided for testing.")
        print("\nTo test with a real ELF file, run:")
        print("  python test_elf_parser.py <path_to_elf_file>")
        print("\nExample:")
        print("  python test_elf_parser.py C:\\path\\to\\firmware.elf")
        print("\n" + "="*70)
        return
    
    elf_path = sys.argv[1]
    """
    print("="*70)
    print("ELF PARSER TEST - WITH REAL ELF FILE")
    print("="*70)
    print(f"\nTesting with file: {elf_path}\n")
    
    try:
        # Test 1: Initialize parser
        print("[TEST 1] Initializing ELF Parser...")
        parser = ELFParser(elf_path)
        print("✓ Parser initialized successfully\n")
        
        # Test 2: Extract symbols
        print("[TEST 2] Extracting symbols...")
        symbols = parser.extract_symbols()
        print(f"✓ Extracted {len(symbols)} symbols\n")
        
        # Test 3: Extract functions
        print("[TEST 3] Extracting functions...")
        functions = parser.extract_functions()
        print(f"✓ Extracted {len(functions)} functions\n")
        
        # Test 4: Get function names
        print("[TEST 4] Getting function names...")
        func_names = parser.get_function_names()
        print(f"✓ Retrieved {len(func_names)} function names")
        if func_names:
            print(f"  Examples: {', '.join(func_names[:5])}\n")
        
        # Test 5: Get global variables
        print("[TEST 5] Getting global variables...")
        variables = parser.get_global_variables()
        print(f"✓ Found {len(variables)} global variables")
        if variables:
            print(f"  Examples: {', '.join([v.name for v in variables[:5]])}\n")
        
        # Test 6: Search for symbols
        print("[TEST 6] Testing symbol search...")
        if func_names:
            test_func = func_names[0]
            results = parser.search_symbol(test_func, exact=True)
            print(f"✓ Exact search for '{test_func}': {len(results)} result(s)")
            
            # Test substring search
            results = parser.search_symbol("main", exact=False)
            print(f"✓ Substring search for 'main': {len(results)} result(s)\n")
        
        # Test 7: Get statistics
        print("[TEST 7] Getting statistics...")
        stats = parser.get_statistics()
        print("✓ Statistics:")
        for key, value in stats.items():
            print(f"    {key:20s}: {value}")
        print()
        
        # Test 8: Export to dictionary
        print("[TEST 8] Exporting to dictionary...")
        data_dict = parser.export_to_dict()
        print(f"✓ Exported data structure with {len(data_dict)} top-level keys")
        print(f"  Keys: {', '.join(data_dict.keys())}\n")
        
        # Display detailed results
        print("="*70)
        print("DETAILED RESULTS")
        print("="*70)
        
        print("\n📊 Symbol Type Distribution:")
        type_counts = {}
        for sym in symbols:
            type_counts[sym.symbol_type] = type_counts.get(sym.symbol_type, 0) + 1
        for sym_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {sym_type:15s}: {count:5d}")
        
        print("\n🔧 Sample Functions (first 15):")
        for i, func in enumerate(functions[:15], 1):
            print(f"  {i:2d}. {func.name:40s} @ 0x{func.address:08x} (size: {func.size})")
        
        print("\n🌍 Sample Global Variables (first 15):")
        for i, var in enumerate(variables[:15], 1):
            print(f"  {i:2d}. {var.name:40s} (size: {var.size} bytes)")
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED! ✓")
        print("="*70)
        
    except FileNotFoundError as e:
        print(f"✗ ERROR: {e}")
        print("\nPlease provide a valid path to an ELF file.")
    except ValueError as e:
        print(f"✗ ERROR: {e}")
        print("\nThe file may not be a valid ELF file.")
    except Exception as e:
        print(f"✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_with_real_elf()

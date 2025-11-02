
"""
Quick test script to verify all required libraries are installed correctly.
"""

def test_imports():
    """Test if all required libraries can be imported."""
    
    print("Testing library imports...\n")
    
    try:
        import PySide6
        from PySide6.QtWidgets import QApplication
        print("✓ PySide6 imported successfully")
        print(f"  Version: {PySide6.__version__}")
    except ImportError as e:
        print(f"✗ PySide6 import failed: {e}")
    
    try:
        import elftools
        from elftools.elf.elffile import ELFFile
        print("✓ pyelftools imported successfully")
        print(f"  Version: {elftools.__version__}")
    except ImportError as e:
        print(f"✗ pyelftools import failed: {e}")
    
    try:
        import pandas as pd
        print("✓ pandas imported successfully")
        print(f"  Version: {pd.__version__}")
    except ImportError as e:
        print(f"✗ pandas import failed: {e}")
    
    try:
        from fuzzywuzzy import fuzz, process
        print("✓ fuzzywuzzy imported successfully")
    except ImportError as e:
        print(f"✗ fuzzywuzzy import failed: {e}")
    
    try:
        import Levenshtein
        print("✓ python-Levenshtein imported successfully")
        print(f"  Version: {Levenshtein.__version__}")
    except ImportError as e:
        print(f"✗ python-Levenshtein import failed: {e}")
    
    try:
        import PyInstaller
        print("✓ PyInstaller imported successfully")
        print(f"  Version: {PyInstaller.__version__}")
    except ImportError as e:
        print(f"✗ PyInstaller import failed: {e}")
    
    print("\n" + "="*50)
    print("Import test complete!")
    print("="*50)


if __name__ == "__main__":
    test_imports()

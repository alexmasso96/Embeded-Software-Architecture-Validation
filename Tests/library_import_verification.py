"""
Quick test script to verify all required libraries are installed correctly.
The checked packages mirror requirements.txt.
"""

import importlib


# (import name, friendly label) — names match the actual runtime dependencies.
REQUIRED = [
    ("PyQt6", "PyQt6"),
    ("PyQt6.QtWidgets", "PyQt6.QtWidgets"),
    ("elftools", "pyelftools"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("rapidfuzz", "rapidfuzz"),
    ("capstone", "capstone"),
    ("bcrypt", "bcrypt"),
    ("PyInstaller", "PyInstaller"),
]


def test_imports():
    """Verify all required libraries can be imported; fail if any are missing."""

    print("Testing library imports...\n")

    missing = []
    for module_name, label in REQUIRED:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", None)
            if version:
                print(f"✓ {label} imported successfully (version {version})")
            else:
                print(f"✓ {label} imported successfully")
        except ImportError as e:
            print(f"✗ {label} import failed: {e}")
            missing.append(label)

    print("\n" + "=" * 50)
    print("Import test complete!")
    print("=" * 50)

    assert not missing, f"Missing required libraries: {', '.join(missing)}"


if __name__ == "__main__":
    test_imports()

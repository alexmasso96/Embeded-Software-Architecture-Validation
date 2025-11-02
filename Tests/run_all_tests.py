import subprocess
from pathlib import Path

test_files = [
    "Tests/library_import_verification.py",
    "Tests/test_elf_parser.py",
    # Add other test files here e.g. "Tests/other_test_file.py"
    ]

project_root = Path(__file__).parent.parent.resolve()

for test in test_files:
    test_path = project_root / test
    print("=" * 70)
    print(f"\nRunning test: {test_path}...")
    print("=" * 70)
    subprocess.run(["python", str(test_path)])

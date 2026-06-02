import subprocess
import sys
from pathlib import Path

test_files = [
    "Tests/library_import_verification.py",
    "Tests/verify_models.py",
    "Tests/test_excel_import.py",
    "Tests/test_elf_parser.py",
    "Tests/test_test_case_design.py",
    "Tests/test_test_case_design_conditional.py",
    "Tests/test_baseline.py",
    "Tests/test_baseline_soft_delete.py",
    "Tests/test_project_isolation.py",
    "Tests/test_elf_parser_cache.py",
    "Tests/test_release_uniqueness.py",
    "Tests/test_column_locking.py",
    "Tests/test_release_elf_data.py",
]

project_root = Path(__file__).parent.parent.resolve()

for test in test_files:
    test_path = project_root / test
    print("=" * 70)
    print(f"\nRunning test: {test_path}...")
    print("=" * 70)
    # Use sys.executable to ensure we run under the same virtual environment.
    # All tests are non-interactive (bundled fixtures / mocked dialogs).
    subprocess.run([sys.executable, str(test_path)])

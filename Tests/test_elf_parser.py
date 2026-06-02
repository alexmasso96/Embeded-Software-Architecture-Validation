import os
import sys
import pytest
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.elf_parser import ELFParser

# Bundled ELF fixture (see Tests/Resources/sample_elf_source.c for the source).
# Set ARCH_TEST_ELF to point the test at a different real ELF binary instead.
DEFAULT_ELF = str(Path(__file__).parent / 'Resources' / 'sample.elf')


def test_with_real_elf():
    elf_path = os.environ.get('ARCH_TEST_ELF', DEFAULT_ELF)
    assert os.path.exists(elf_path), f"Test ELF not found: {elf_path}"

    parser = ELFParser()
    parser.load_elf(elf_path)
    parser.extract_symbols()
    parser.extract_functions()

    assert parser.functions is not None and len(parser.functions) > 0
    assert parser.symbols is not None and len(parser.symbols) > 0
    assert parser.md5_hash is not None and len(parser.md5_hash) == 32

    # ensure it's a hex string
    int(parser.md5_hash, 16)


if __name__ == "__main__":
    test_with_real_elf()
    print("ELF parser test passed.")

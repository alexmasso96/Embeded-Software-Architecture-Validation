"""
ELF Parser Module
=================
Extracts symbols, functions, and parameters from ELF binary files.
Uses pyelftools library for low-level ELF file parsing.
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from pathlib import Path
import logging

try:
    from elftools.elf.elffile import ELFFile
    from elftools.elf.sections import SymbolTableSection
    from elftools.dwarf.descriptions import describe_form_class
except ImportError as e:
    raise ImportError(
        "pyelftools is required for ELF parsing. "
        "Install it with: pip install pyelftools"
    ) from e


#configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Symbol:
    """Represents a symbol extracted from an ELF file."""
    name: str
    address: int
    size: int
    symbol_type: str #FUNC, OBJECT, NOTYPE, etc.
    binding: str
    section: str

    def __str__(self):
        return (f"Symbol(name='{self.name}', type={self.symbol_type}, "
                f"bindings={self.binding}, addr=0x{self.address:08x}, size = {self.size})")


@dataclass
class Function:
    """Represents a function extracted from an ELF file."""
    name: str
    address: int
    size: int
    parameters: List[str] # Parameter names (if available from DWARF)
    return_type: Optional[str] = None

    def __str__(self):
        params = ', '.join(self.parameters) if self.parameters else 'unknown'
        return f"Function(name='{self.name}', params=[{params}], addr=0x{self.address:08x}, size={self.size})"


class ELFParser:
    """
    Parser for ELF binary files to extract symbols and functions.

    This class provides methods to:
    - Load and parse ELF files
    - Extract function symbols
    - Extract global variables/objects
    - Get detailed symbol information
    """

    def __init__(self, elf_path: str):
        """
        Initialize the ELF parser with the given ELF file path.

        Args:
            elf_path: Path to the ELF file

        Raises:
            FileNotFoundError: If the ELF file does not exist.
            ValueError: If the file is not a valid ELF file.
        """
        self.elf_path = Path(elf_path)

        if not self.elf_path.exists():
            raise FileNotFoundError(f"ELF file not found: {elf_path}")

        self.elf_file = None
        self.symbols: List[Symbol] = []
        self.functions: List[Function] = []
        self._load_elf()

    def _load_elf(self):
        """Load and validate the ELF file."""

        try:
            with open(self.elf_path, 'rb') as f:
                self.elf_file = ELFFile(f)
                if not self.elf_file:
                    raise ValueError(f"Invalid ELF file: {self.elf_path}")
                logger.info(f"Successfully loaded ELF file: {self.elf_path}")
                logger.info(f"ELF Architecture {self.elf_file.get_machine_arch()}")
        except Exception as e:
            raise ValueError(f"Failed to load ELF file: {e}") from e

    def extract_symbols(self):
        """
        Extracts symbols from an ELF file's symbol table.

        Returns:
            List of Symbol objects.
        """
        if self.symbols:
            return self.symbols

        logger.info("Extracting symbols from ELF file")

        with open(self.elf_path, 'rb') as f:
            elffile = ELFFile(f)

            # Iterate through all sections to find symbol tables
            for section in elffile.iter_sections():
                if isinstance(section, SymbolTableSection):
                    logger.info(f"Found symbol table: {section.name}")

                    for symbol in section.iter_symbols():
                        # Skip unnamed symbols
                        if not symbol.name:
                            continue

                        # Get symbol type and binding
                        sym_type = symbol['st_info']['type']
                        sym_bind = symbol['st_info']['bind']

                        # Get section name
                        if symbol['st_shndx'] == 'SHN_UNDEF':
                            section_name = 'UNDEF'
                        elif symbol['st_shndx'] == 'SHN_ABS':
                            section_name = 'ABS'
                        else:
                            try:
                                section_name = elffile.get_section(symbol['st_shndx']).name
                            except:
                                section_name = 'UNKNOWN'

                        sym_obj = Symbol(
                            name = symbol.name,
                            address = symbol['st_value'],
                            size = symbol['st_size'],
                            symbol_type = sym_type,
                            binding = sym_bind,
                            section = section_name
                        )

                        self.symbols.append(sym_obj)

        logger.info(f"Extracted {len(self.symbols)} symbols")
        return self.symbols

    def extract_functions(self) -> List[Function]:
        """
        Extracts function symbols from the ELF file.

        Returns:
            List of Function objects.
        """
        if self.functions:
            return self.functions

        # First extract all symbols if not already done
        if not self.symbols:
            self.extract_symbols()

        #Filter for function symbols
        logger.info("Filtering function symbols...")

        for symbol in self.symbols:
            if symbol.symbol_type == 'STT_FUNC':
                func = Function(
                    name = symbol.name,
                    address = symbol.address,
                    size = symbol.size,
                    parameters = [] #will be populated by DWARF parsing if available
                )
                self.functions.append(func)
        logger.info(f"Found {len(self.functions)} functions")
        return self.functions

    def get_function_names(self) -> List[Function]:
        """
        Gets a list of all function names.

        Returns:
            List of function name strings.
        """
        if not self.functions:
            self.extract_functions()

        return [func.name for func in self.functions]

    def get_global_variables(self) -> List[Symbol]:
        """
        Extract global variables/objects from the ELF file.

        Returns:
            List of Symbol objects that are global variables.
        """

        if not self.symbols:
            self.extract_symbols()

        variables = [
            sym for sym in self.symbols
            if sym.symbol_type == 'STT_OBJECT' and sym.binding in ['STB_GLOBAL', 'STB_WEAK']
        ]

        logger.info(f"Found {len(variables)} global variables")
        return variables

    def search_symbol(self, name: str, exact: bool = True) -> List[Symbol]:
        """
        Search for symbols by name.

        Args:
            name: Symbol name to search for.
            exact: If True, match exact name. If False, match substring

        Returns:
            List of matching symbols.
        """
        if not self.symbols:
            self.extract_symbols()

        if exact:
            return [sym for sym in self.symbols if sym.name == name]
        else:
            return [sym for sym in self.symbols if name.lower() in sym.name.lower()]

    def get_symbol_by_address(self, address: int) -> Optional[Symbol]:
        """
        Find a symbol at a specific address.

        Args:
            address: Memory address to search

        Return:
            Symbol object if found, None otherwise.
        """
        if not self.symbols:
            self.extract_symbols()

        for sym in self.symbols:
            if sym.address == address:
                return sym

        return None

    def get_statistics(self) -> Dict[str, int]:
        """
        Gets statistics about the ELF file.

        Returns:
            Dictionary with symbol counts by type
        """
        if not self.symbols:
            self.extract_symbols()

        stats = {
            'total_symbols': len(self.symbols),
            'functions': len([s for s in self.symbols if s.symbol_type == 'STT_FUNC']),
            'objects': len([s for s in self.symbols if s.symbol_type == 'STT_OBJECT']),
            'global_symbols': len([s for s in self.symbols if s.binding == 'STT_GLOBAL']),
            'local_symbols': len([s for s in self.symbols if s.binding == 'STT_LOCAL']),
            'weak_symbols': len([s for s in self.symbols if s.binding == 'STT_WEAK'])
        }

        return stats

    def export_to_dict(self) -> Dict:
        """
        Exports all parsed data to a dictionary format
        Useful for JSON serialization or data persistence.

        Returns:
            Dictionary with all symbols and functions
        """
        if not self.symbols:
            self.extract_symbols()

        if not self.functions:
            self.extract_functions()

        return {
            'elf_path': str(self.elf_path),
            'Symbols': [
                {
                    'name': s.name,
                    'address': s.address,
                    'size': s.size,
                    'type': s.symbol_type,
                    'binding': s.binding,
                    'section':s.section,
                }
                for s in self.symbols
            ],
            'Functions': [
                {
                    'name': f.name,
                    'address':f.address,
                    'size': f.size,
                    'parameters': f.parameters
                }
                for f in self.functions
            ],
            'statistics': self.get_statistics()
        }

def main():
    """For testing purposes only!"""

    import sys

    print("Enter the path to the .elf file: ")
    elf_path = input()

    try:
        #Create parser instance

        parser = ELFParser(elf_path)

        # Extract and display statistics
        print("\n" + "="*60)
        print("ELF FILE ANALYSIS")
        print("="*60)
        print(f"File: {elf_path}")

        stats = parser.get_statistics()
        for key, value in stats.items():
            print(f"{key:20s}: {value}")

        #Display first 10 global variables
        functions = parser.get_function_names()
        print(f"\nFirst 10 Functions (out of {len(functions)}): ")
        for func_name in functions[:10]:
            print(f" - {func_name}")

        #Display first 10 global variables
        variables = parser.get_global_variables()
        print(f"\nFirst 10 Global Variables (out of {len(variables)}): ")
        for var in variables[:10]:
            print(f" - {var.name}(size: {var.size} bytes)")

        print("\n" + "="*60)
        print("Parsing completed successfully!")
        print("="*60)

    except Exception as e:
        logger.error(f"Error parsing ELF file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
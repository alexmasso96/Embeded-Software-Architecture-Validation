"""
ELF Parser Module
=================
Extracts symbols, functions, and parameters from ELF binary files.
Uses pyelftools library for low-level ELF file parsing.
"""

from typing import List, Dict, Optional, Set, Union, Generator
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import collections
import sys
import bisect
import json
import hashlib
import os
import gc

try:
    from elftools.elf.elffile import ELFFile
    from elftools.elf.sections import SymbolTableSection
    from elftools.dwarf.descriptions import describe_form_class
except ImportError as e:
    raise ImportError(
        "pyelftools is required for ELF parsing. "
        "Install it with: pip install pyelftools"
    ) from e

try:
    import capstone
    from capstone import (
        Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM, 
        CS_ARCH_X86, CS_MODE_32, CS_MODE_64, 
        CS_ARCH_ARM64, 
        CS_ARCH_MIPS, CS_MODE_MIPS32,
        CS_ARCH_TRICORE, CS_MODE_TRICORE_162
    )
    CAPSTONE_AVAILABLE = True
except ImportError:
    CAPSTONE_AVAILABLE = False
    pass


#configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Symbol:
    """Represents a symbol extracted from an ELF file."""
    __slots__ = ['name', 'address', 'size', 'symbol_type', 'binding', 'section']
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
    __slots__ = ['name', 'address', 'size', 'parameters', 'return_type']
    name: str
    address: int
    size: int
    parameters: List[Dict[str, str]] # List of {'name': str, 'type': str}
    return_type: Optional[str]

    def __init__(self, name: str, address: int, size: int, parameters: List[Dict[str, str]], return_type: Optional[str] = None):
        self.name = name
        self.address = address
        self.size = size
        self.parameters = parameters
        self.return_type = return_type

    def __str__(self):
        params_str = []
        for p in self.parameters:
            if isinstance(p, dict):
                params_str.append(f"{p['name']}: {p.get('type', 'unknown')}")
            else:
                params_str.append(str(p))
        params = ', '.join(params_str) if params_str else 'void'
        return f"Function(name='{self.name}', params=[{params}], addr=0x{self.address:08x}, size={self.size})"


class ELFParser:
    """
    Parser for ELF binary files to extract symbols and functions.
    """

    def __init__(self, elf_path: str = None):
        self.elf_path = Path(elf_path) if elf_path else None
        self.stream = None
        self.elf_file = None
        self.symbols: List[Symbol] = []
        self.functions: List[Function] = []
        self.structures: Dict[str, List[Dict[str, str]]] = {}
        self.global_vars_dwarf: Dict[str, str] = {}
        
        self._func_addr_map: Dict[int, Function] = {}
        self._sorted_func_addrs: List[int] = []
        self.md5_hash = None

    def load_elf(self, elf_path: str):
        """Loads and parses an ELF file."""
        self.elf_path = Path(elf_path)
        if not self.elf_path.exists():
            raise FileNotFoundError(f"ELF file not found: {elf_path}")
            
        self.md5_hash = self._calculate_md5()
        
        try:
            self.stream = open(self.elf_path, 'rb')
            self._load_elf_file()
        except Exception as e:
            self.close()
            raise e

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Closes the open file stream."""
        if self.stream:
            self.stream.close()
            self.stream = None
        # Clear large lists to free memory
        self.symbols = []
        self.functions = []
        self.structures = {}
        self._func_addr_map = {}
        self._sorted_func_addrs = []
        gc.collect()

    def _calculate_md5(self):
        """Calculates MD5 hash of the ELF file."""
        hash_md5 = hashlib.md5()
        with open(self.elf_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _load_elf_file(self):
        """Load and validate the ELF file."""
        try:
            self.stream.seek(0)
            self.elf_file = ELFFile(self.stream)
            if not self.elf_file:
                raise ValueError(f"Invalid ELF file: {self.elf_path}")
            logger.info(f"Successfully loaded ELF file: {self.elf_path}")
            logger.info(f"ELF Architecture {self.elf_file.get_machine_arch()}")
        except Exception as e:
            raise ValueError(f"Failed to load ELF file: {e}") from e

    def save_cache(self, cache_path: str):
        """Saves parsed data to a JSON cache file."""
        try:
            # Convert objects to dicts for JSON serialization
            # We do this generator-style to avoid creating a massive list of dicts in memory
            
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            with open(cache_path, 'w') as f:
                # Manually construct JSON to stream data
                f.write('{\n')
                f.write(f'  "elf_path": "{str(self.elf_path)}",\n')
                f.write(f'  "elf_hash": "{self.md5_hash}",\n')
                
                f.write('  "symbols": [\n')
                for i, s in enumerate(self.symbols):
                    json_str = json.dumps(asdict(s))
                    f.write('    ' + json_str + (',' if i < len(self.symbols) - 1 else '') + '\n')
                f.write('  ],\n')

                f.write('  "functions": [\n')
                for i, func in enumerate(self.functions):
                    # Manual serialization for Function because of __slots__ and potential complexity
                    func_dict = {
                        'name': func.name,
                        'address': func.address,
                        'size': func.size,
                        'parameters': func.parameters,
                        'return_type': func.return_type
                    }
                    json_str = json.dumps(func_dict)
                    f.write('    ' + json_str + (',' if i < len(self.functions) - 1 else '') + '\n')
                f.write('  ],\n')

                f.write(f'  "structures": {json.dumps(self.structures)},\n')
                f.write(f'  "global_vars": {json.dumps(self.global_vars_dwarf)}\n')
                f.write('}')
                
            logger.info(f"Cache saved to {cache_path}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def load_cache(self, cache_path: str) -> bool:
        """Loads parsed data from a JSON cache file."""
        if not os.path.exists(cache_path):
            return False
            
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            self.elf_path = Path(data.get("elf_path", ""))
            self.md5_hash = data.get("elf_hash")
            
            # Clear existing data before loading
            self.symbols = []
            self.functions = []
            
            self.symbols = [Symbol(**s) for s in data["symbols"]]
            self.functions = [Function(**f) for f in data["functions"]]
            self.structures = data["structures"]
            self.global_vars_dwarf = data["global_vars"]
            
            # We need to open the ELF file for Capstone/disassembly to work later
            if self.elf_path and self.elf_path.exists():
                try:
                    self.stream = open(self.elf_path, 'rb')
                    self._load_elf_file()
                except Exception as e:
                    logger.warning(f"Could not open original ELF file {self.elf_path}: {e}. Disassembly will not work.")
            
            self._build_function_address_map()
            logger.info("Loaded data from cache.")
            return True
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return False

    def _normalize_address(self, address: int) -> int:
        """Normalizes an address for lookup, e.g., removing Thumb bit for ARM."""
        if self.elf_file and self.elf_file.get_machine_arch() == 'ARM':
            return address & ~1
        return address

    def _build_function_address_map(self):
        """Builds a map of function start addresses for quick lookups."""
        if not self.functions and not self.symbols:
             return

        self._func_addr_map = {self._normalize_address(f.address): f for f in self.functions}
        self._sorted_func_addrs = sorted(self._func_addr_map.keys())

    def extract_all(self):
        """Runs all extraction methods."""
        # Consume generators into lists for storage
        if not self.symbols:
            self.symbols = list(self._generate_symbols())
        
        if not self.functions:
            self.functions = list(self._generate_functions())
            
        self.extract_function_parameters()
        self.extract_structures()
        self.extract_dwarf_variables()
        self._build_function_address_map()
        
        # Force GC
        gc.collect()

    def _generate_symbols(self) -> Generator[Symbol, None, None]:
        """Generator that yields symbols one by one."""
        logger.info("Extracting symbols from ELF file")
        elffile = self.elf_file
        for section in elffile.iter_sections():
            if isinstance(section, SymbolTableSection):
                for symbol in section.iter_symbols():
                    if not symbol.name: continue
                    if symbol['st_shndx'] == 'SHN_UNDEF': section_name = 'UNDEF'
                    elif symbol['st_shndx'] == 'SHN_ABS': section_name = 'ABS'
                    else:
                        try: section_name = elffile.get_section(symbol['st_shndx']).name
                        except: section_name = 'UNKNOWN'
                    
                    yield Symbol(
                        name=symbol.name, address=symbol['st_value'], size=symbol['st_size'],
                        symbol_type=symbol['st_info']['type'], binding=symbol['st_info']['bind'],
                        section=section_name
                    )

    def extract_symbols(self):
        """Public method to populate symbols list."""
        if self.symbols: return self.symbols
        self.symbols = list(self._generate_symbols())
        return self.symbols

    def _generate_functions(self) -> Generator[Function, None, None]:
        """Generator that yields functions one by one."""
        if not self.symbols:
            self.symbols = list(self._generate_symbols())
            
        logger.info("Filtering function symbols...")
        for symbol in self.symbols:
            if symbol.symbol_type == 'STT_FUNC':
                yield Function(
                    name=symbol.name, address=symbol.address, size=symbol.size, parameters=[]
                )

    def extract_functions(self) -> List[Function]:
        """Public method to populate functions list."""
        if self.functions: return self.functions
        self.functions = list(self._generate_functions())
        return self.functions

    def _get_die_from_attribute(self, die, attribute_name):
        if attribute_name not in die.attributes: return None
        attr = die.attributes[attribute_name]
        offset = attr.value
        if hasattr(attr, 'form') and attr.form in ('DW_FORM_ref1', 'DW_FORM_ref2', 'DW_FORM_ref4', 'DW_FORM_ref8', 'DW_FORM_ref_udata'):
             offset += die.cu.cu_offset
        try: return die.cu.dwarfinfo.get_DIE_from_refaddr(offset)
        except: return None

    def _get_type_name(self, type_die) -> str:
        try:
            if not type_die: return "unknown"
            tag = type_die.tag
            name = type_die.attributes['DW_AT_name'].value.decode('utf-8', errors='replace') if 'DW_AT_name' in type_die.attributes else None
            
            if tag == 'DW_TAG_base_type': return name or 'void'
            elif tag == 'DW_TAG_typedef': return name or 'typedef'
            elif tag == 'DW_TAG_structure_type': return f"struct {name}" if name else "struct <anon>"
            elif tag == 'DW_TAG_pointer_type':
                inner = self._get_die_from_attribute(type_die, 'DW_AT_type')
                return f"{self._get_type_name(inner)}*" if inner else "void*"
            elif tag == 'DW_TAG_const_type':
                inner = self._get_die_from_attribute(type_die, 'DW_AT_type')
                return f"const {self._get_type_name(inner)}" if inner else "const void"
            elif tag == 'DW_TAG_volatile_type':
                inner = self._get_die_from_attribute(type_die, 'DW_AT_type')
                return f"volatile {self._get_type_name(inner)}" if inner else "volatile void"
            elif tag == 'DW_TAG_array_type':
                 inner = self._get_die_from_attribute(type_die, 'DW_AT_type')
                 return f"{self._get_type_name(inner)}[]" if inner else "array"
            return name or "unknown"
        except: return "unknown"

    def extract_function_parameters(self) -> None:
        if not self.elf_file.has_dwarf_info(): return
        dwarfinfo = self.elf_file.get_dwarf_info()
        func_map = {f.name: f for f in self.functions}
        for CU in dwarfinfo.iter_CUs():
            for DIE in CU.iter_DIEs():
                if DIE.tag == 'DW_TAG_subprogram' and 'DW_AT_name' in DIE.attributes:
                    try:
                        func_name = DIE.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                        if func_name in func_map:
                            params = []
                            for child in DIE.iter_children():
                                if child.tag == 'DW_TAG_formal_parameter' and 'DW_AT_name' in child.attributes:
                                    p_name = child.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                                    p_type = "unknown"
                                    t_die = self._get_die_from_attribute(child, 'DW_AT_type')
                                    if t_die: p_type = self._get_type_name(t_die)
                                    params.append({'name': p_name, 'type': p_type})
                            func_map[func_name].parameters = params
                    except: pass

    def extract_structures(self) -> Dict[str, List[Dict[str, str]]]:
        if self.structures: return self.structures
        if not self.elf_file.has_dwarf_info(): return {}
        logger.info("Extracting structures from DWARF info...")
        typedefs = []
        try:
            dwarfinfo = self.elf_file.get_dwarf_info()
            for CU in dwarfinfo.iter_CUs():
                for DIE in CU.iter_DIEs():
                    if DIE.tag in ('DW_TAG_structure_type', 'DW_TAG_class_type', 'DW_TAG_union_type'):
                        if 'DW_AT_declaration' in DIE.attributes and DIE.attributes['DW_AT_declaration'].value: continue
                        s_name = None
                        if 'DW_AT_name' in DIE.attributes: s_name = DIE.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                        elif 'DW_AT_specification' in DIE.attributes:
                            spec = self._get_die_from_attribute(DIE, 'DW_AT_specification')
                            if spec and 'DW_AT_name' in spec.attributes: s_name = spec.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                        
                        if s_name:
                            fields = []
                            for child in DIE.iter_children():
                                if child.tag in ('DW_TAG_member', 'DW_TAG_field'):
                                    f_name = child.attributes['DW_AT_name'].value.decode('utf-8', errors='replace') if 'DW_AT_name' in child.attributes else "<anonymous>"
                                    f_type = "unknown"
                                    t_die = self._get_die_from_attribute(child, 'DW_AT_type')
                                    if t_die: f_type = self._get_type_name(t_die)
                                    fields.append({'name': f_name, 'type': f_type})
                                elif child.tag == 'DW_TAG_inheritance':
                                    t_die = self._get_die_from_attribute(child, 'DW_AT_type')
                                    if t_die: fields.append({'name': '<base>', 'type': self._get_type_name(t_die)})
                            if fields or s_name not in self.structures: self.structures[s_name] = fields
                    elif DIE.tag == 'DW_TAG_typedef': typedefs.append(DIE)
            
            for DIE in typedefs:
                if 'DW_AT_name' not in DIE.attributes: continue
                td_name = DIE.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                seen = set()
                t_die = self._get_die_from_attribute(DIE, 'DW_AT_type')
                while t_die and t_die.offset not in seen:
                    seen.add(t_die.offset)
                    if t_die.tag in ('DW_TAG_const_type', 'DW_TAG_volatile_type', 'DW_TAG_typedef'): t_die = self._get_die_from_attribute(t_die, 'DW_AT_type')
                    else: break
                
                if t_die and t_die.tag in ('DW_TAG_structure_type', 'DW_TAG_class_type', 'DW_TAG_union_type'):
                    if 'DW_AT_declaration' in t_die.attributes and t_die.attributes['DW_AT_declaration'].value:
                        if 'DW_AT_name' in t_die.attributes:
                            target = t_die.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                            if target in self.structures: self.structures[td_name] = self.structures[target]
                        continue
                    fields = []
                    for child in t_die.iter_children():
                        if child.tag in ('DW_TAG_member', 'DW_TAG_field'):
                            f_name = child.attributes['DW_AT_name'].value.decode('utf-8', errors='replace') if 'DW_AT_name' in child.attributes else "<anonymous>"
                            f_type = "unknown"
                            tt_die = self._get_die_from_attribute(child, 'DW_AT_type')
                            if tt_die: f_type = self._get_type_name(tt_die)
                            fields.append({'name': f_name, 'type': f_type})
                        elif child.tag == 'DW_TAG_inheritance':
                             tt_die = self._get_die_from_attribute(child, 'DW_AT_type')
                             if tt_die: fields.append({'name': '<base>', 'type': self._get_type_name(tt_die)})
                    if td_name not in self.structures or fields: self.structures[td_name] = fields
        except: pass
        
        # Clear large temp list
        del typedefs
        gc.collect()
        return self.structures

    def extract_dwarf_variables(self) -> Dict[str, str]:
        if self.global_vars_dwarf: return self.global_vars_dwarf
        if not self.elf_file.has_dwarf_info(): return {}
        logger.info("Extracting variables from DWARF info...")
        try:
            dwarfinfo = self.elf_file.get_dwarf_info()
            for CU in dwarfinfo.iter_CUs():
                top = CU.get_top_DIE()
                for child in top.iter_children():
                    if child.tag == 'DW_TAG_variable' and 'DW_AT_name' in child.attributes:
                        try:
                            name = child.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
                            v_type = "unknown"
                            t_die = self._get_die_from_attribute(child, 'DW_AT_type')
                            if t_die: v_type = self._get_type_name(t_die)
                            self.global_vars_dwarf[name] = v_type
                        except: continue
        except: pass
        return self.global_vars_dwarf

    def search_function(self, name:str, exact: bool = False) -> List[Function]:
        if not self.functions: self.extract_functions()
        name = name.strip()
        filtered = [f for f in self.functions if "_EXIT_" not in f.name and not f.name.endswith("_function_end")]
        if exact: return [f for f in filtered if f.name == name]
        results = [f for f in filtered if name.lower() in f.name.lower()]
        results.sort(key=lambda f: f.name != name)
        return results

    def get_symbol_by_address(self, address: int) -> Optional[Symbol]:
        if not self.symbols: self.extract_symbols()
        for sym in self.symbols:
            if sym.address == address: return sym
        return None

    def get_function_containing_address(self, address: int) -> Optional[Function]:
        if not self._sorted_func_addrs: self._build_function_address_map()
        norm_addr = self._normalize_address(address)
        idx = bisect.bisect_right(self._sorted_func_addrs, norm_addr)
        if idx == 0: return None
        candidate = self._func_addr_map[self._sorted_func_addrs[idx - 1]]
        if candidate.size > 0 and candidate.address <= norm_addr < (candidate.address + candidate.size):
            return candidate
        return None

    def _get_capstone_instance(self, address: int = 0):
        if not CAPSTONE_AVAILABLE or not self.elf_file: return None
        arch = self.elf_file.get_machine_arch()
        try:
            if arch == 'ARM': return capstone.Cs(CS_ARCH_ARM, CS_MODE_THUMB if address & 1 else CS_MODE_ARM)
            elif arch == 'AArch64': return capstone.Cs(CS_ARCH_ARM64, CS_MODE_ARM)
            elif arch in ['x86', 'Intel 80386']: return capstone.Cs(CS_ARCH_X86, CS_MODE_32)
            elif arch in ['x64', 'AMD64', 'x86-64']: return capstone.Cs(CS_ARCH_X86, CS_MODE_64)
            elif arch == 'MIPS': return capstone.Cs(CS_ARCH_MIPS, CS_MODE_MIPS32)
            elif 'TriCore' in arch: return capstone.Cs(CS_ARCH_TRICORE, CS_MODE_TRICORE_162)
        except: return None
        return None

    def get_function_bytes(self, func: Function) -> bytes:
        if not self.elf_file: return b""
        for section in self.elf_file.iter_sections():
            if section['sh_flags'] & 0x4:
                start = section['sh_addr']
                size = section['sh_size']
                func_addr = self._normalize_address(func.address)
                if start <= func_addr < start + size:
                    offset = func_addr - start
                    read_size = size - offset if offset + func.size > size else func.size
                    return section.data()[offset : offset + read_size]
        return b""

    def extract_subcalls(self, func_name: str) -> List[str]:
        if not CAPSTONE_AVAILABLE: return ["Capstone not installed"]
        func = next((f for f in self.functions if f.name == func_name), None)
        if not func: return ["Function not found"]
        
        # If size is 0, try to estimate it from next function
        if func.size == 0:
            start_addr = self._normalize_address(func.address)
            idx = bisect.bisect_right(self._sorted_func_addrs, start_addr)
            if idx < len(self._sorted_func_addrs):
                next_addr = self._sorted_func_addrs[idx]
                func.size = next_addr - start_addr
            else:
                func.size = 0x200 # Fallback default size
        
        code = self.get_function_bytes(func)
        if not code: return ["Could not retrieve function code"]

        md = self._get_capstone_instance(func.address)
        if not md: return ["Capstone init failed"]
        
        # Enable skipdata to skip unknown instructions
        md.skipdata = True
        
        calls = set()
        start_addr = self._normalize_address(func.address)
        
        instruction_count = 0
        try:
            # Use disasm generator to avoid loading all instructions into memory
            for insn in md.disasm(code, start_addr):
                instruction_count += 1
                # Added CALLA, FCALL for TriCore
                if insn.mnemonic.upper() in ['CALL', 'BL', 'BLX', 'JAL', 'JALR', 'JL', 'CALLA', 'FCALL']:
                    if len(insn.operands) > 0:
                        op = insn.operands[0]
                        if op.type == 2: # IMM
                            # Fix: Mask address to 32-bit to avoid signed/unsigned mismatch issues
                            target = op.imm & 0xFFFFFFFF
                            norm_target = self._normalize_address(target)
                            
                            # Priority 1: Exact Function Match from Map
                            if norm_target in self._func_addr_map:
                                calls.add(self._func_addr_map[norm_target].name)
                            else:
                                # Priority 2: Containing Function
                                cont_func = self.get_function_containing_address(target)
                                if cont_func: calls.add(cont_func.name)
                                else:
                                    # Priority 3: Symbol Table
                                    sym = self.get_symbol_by_address(target)
                                    if sym: calls.add(sym.name)
                                    else: calls.add(f"0x{target:x}")
        except Exception as e:
            return [f"Disassembly error: {e}"]
            
        if instruction_count == 0:
            return ["No instructions disassembled (check architecture/mode)"]

        return sorted(list(calls))

    def get_statistics(self) -> Dict[str, int]:
        if not self.symbols: self.extract_symbols()
        return {
            'total_symbols': len(self.symbols),
            'functions': len([s for s in self.symbols if s.symbol_type == 'STT_FUNC']),
            'objects': len([s for s in self.symbols if s.symbol_type == 'STT_OBJECT']),
        }

def main():
    project_root = Path(os.getcwd())
    resources_dir = project_root / "Resources"
    resources_dir.mkdir(exist_ok=True)

    print("\n" + "="*60)
    print("ELF PARSER - MAIN MENU")
    print("="*60)
    print("1. Load New ELF File")
    print("2. Load JSON Database")
    print("q. Quit")
    
    choice = input("\n> ").strip().lower()
    if choice == 'q': return

    parser = ELFParser()
    
    if choice == '1':
        print("Enter the path to the .elf file: ")
        elf_path = input().strip()
        cache_file = resources_dir / (Path(elf_path).name + ".json")
        
        try:
            parser.load_elf(elf_path)
            
            loaded_from_cache = False
            if cache_file.exists():
                # Check cache
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                if data.get("elf_hash") == parser.md5_hash:
                    print(f"\nCache found for {Path(elf_path).name} and matches ELF.")
                    print("Load from cache? (Y/n)")
                    if input("> ").strip().lower() != 'n':
                        if parser.load_cache(str(cache_file)):
                            loaded_from_cache = True
                else:
                    print("\nCache found but MD5 mismatch. Re-parsing ELF...")
            
            if not loaded_from_cache:
                print("Parsing ELF file (this may take a moment)...")
                parser.extract_all()
                print("Saving to cache...")
                parser.save_cache(str(cache_file))
                
        except Exception as e:
            logger.error(f"Error loading ELF: {e}")
            return

    elif choice == '2':
        json_files = list(resources_dir.glob("*.json"))
        if not json_files:
            print("No JSON databases found in Resources folder.")
            return
            
        print("\nAvailable Databases:")
        for i, f in enumerate(json_files, 1):
            print(f"{i}. {f.name}")
            
        print("\nSelect database to load:")
        try:
            idx = int(input("> ").strip())
            if 1 <= idx <= len(json_files):
                target_json = json_files[idx-1]
                print(f"Loading {target_json.name}...")
                if not parser.load_cache(str(target_json)):
                    print("Failed to load cache.")
                    return
            else:
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid input.")
            return
    else:
        print("Invalid selection.")
        return

    # Main Interaction Loop
    try:
        # Helper for printing tree
        def print_struct_tree(struct_name, indent="  ", visited=None):
            if visited is None: visited = set()
            if struct_name in visited:
                print(f"{indent}...(recursive {struct_name})")
                return
            visited.add(struct_name)
            
            if struct_name in parser.structures:
                print(f"{indent}Structure: {struct_name}")
                for field in parser.structures[struct_name]:
                    f_name, f_type = field['name'], field['type']
                    base = f_type.replace('*','').replace('const ','').replace('volatile ','').replace('struct ','').strip()
                    if base in parser.structures:
                        print(f"{indent}  - {f_name}: {f_type}")
                        print_struct_tree(base, indent + "    ", visited.copy())
                    else:
                        print(f"{indent}  - {f_name}: {f_type}")

        while True:
            print("\n" + "=" * 60)
            print("Select Search Mode:")
            print("1. Search Functions (shows subcalls)")
            print("2. Search Parameters/Structures (shows content)")
            print("q. Quit")
            print("="*60)
            
            mode = input("\n> ").strip().lower()
            if mode == 'q': break
            
            if mode == '1':
                print("Enter function name to search:")
                usr_fct = input("> ").strip()
                if not usr_fct: continue
                
                results = parser.search_function(usr_fct)
                if not results:
                    print("No functions found.")
                    continue
                    
                for idx, result in enumerate(results, 1):
                    print(f"\n{idx}: {result.name} (Addr: 0x{result.address:08x})")
                    
                print ("\nEnter index to show details (or 0 to skip): ")
                try:
                    idx = int(input("> ").strip())
                    if 1 <= idx <= len(results):
                        func = results[idx - 1]
                        print(f"\nFunction: {func.name}")
                        print(f"  Address: 0x{func.address:08x}")
                        print(f"  Parameters:")
                        for param in func.parameters:
                            print(f"    - {param['name']} ({param['type']})")
                        
                        print(f"  Subfunctions called:")
                        subcalls = parser.extract_subcalls(func.name)
                        if not subcalls: print("    (None)")
                        for call in subcalls: print(f"    - {call}")
                except ValueError: pass

            elif mode == '2':
                print("Enter parameter/structure/variable name to search:")
                usr_var = input("> ").strip()
                if not usr_var: continue
                
                # Collect matches
                matches = []
                # Structs
                for s in parser.structures:
                    if usr_var.lower() in s.lower():
                        matches.append(('Struct', s))
                # Vars
                for v, t in parser.global_vars_dwarf.items():
                    if usr_var.lower() in v.lower():
                        matches.append(('Variable', v, t))
                
                if not matches:
                    print("No matches found.")
                    continue
                    
                print(f"\nFound {len(matches)} matches:")
                for i, m in enumerate(matches, 1):
                    if m[0] == 'Struct':
                        print(f"{i}. [Struct] {m[1]}")
                    else:
                        print(f"{i}. [Variable] {m[1]} (Type: {m[2]})")
                        
                print("\nSelect index to explore (or 0 to cancel):")
                try:
                    sel = int(input("> ").strip())
                    if 1 <= sel <= len(matches):
                        selection = matches[sel-1]
                        print("\n" + "-"*40)
                        if selection[0] == 'Struct':
                            print_struct_tree(selection[1])
                        else:
                            v_name, v_type = selection[1], selection[2]
                            print(f"Variable: {v_name}")
                            print(f"Type: {v_type}")
                            base = v_type.replace('*','').replace('const ','').replace('volatile ','').replace('struct ','').strip()
                            if base in parser.structures:
                                print_struct_tree(base, indent="  ")
                except ValueError: pass

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
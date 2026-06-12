use std::collections::{HashMap, HashSet};
use std::fs::File;
use object::{Object, ObjectSymbol, SymbolKind, ObjectSection};
use memmap2::Mmap;
use serde::Serialize;
use rayon::prelude::*;
use pyo3::prelude::*;

fn load_and_relocate_section(
    elf_file: &object::File<'_>,
    section_name: &str,
) -> Vec<u8> {
    let section = match elf_file.section_by_name(section_name) {
        Some(s) => s,
        None => return Vec::new(),
    };
    
    let mut data = section.data().unwrap_or(&[]).to_vec();
    
    for (offset, reloc) in section.relocations() {
        let symbol_value = match reloc.target() {
            object::RelocationTarget::Symbol(idx) => {
                if let Ok(sym) = elf_file.symbol_by_index(idx) {
                    sym.address()
                } else {
                    0
                }
            }
            object::RelocationTarget::Section(idx) => {
                if let Ok(sec) = elf_file.section_by_index(idx) {
                    sec.address()
                } else {
                    0
                }
            }
            _ => 0,
        };
        
        let value = symbol_value.wrapping_add(reloc.addend() as u64);
        
        let size = reloc.size() / 8; // in bytes
        let offset = offset as usize;
        if offset + size as usize <= data.len() {
            let is_little_endian = elf_file.is_little_endian();
            if size == 4 {
                let bytes = if is_little_endian {
                    (value as u32).to_le_bytes()
                } else {
                    (value as u32).to_be_bytes()
                };
                data[offset..offset + 4].copy_from_slice(&bytes);
            } else if size == 8 {
                let bytes = if is_little_endian {
                    value.to_le_bytes()
                } else {
                    value.to_be_bytes()
                };
                data[offset..offset + 8].copy_from_slice(&bytes);
            }
        }
    }
    
    data
}

type Reader<'a> = gimli::EndianSlice<'a, gimli::RunTimeEndian>;

#[derive(Serialize)]
struct Symbol {
    name: String,
    address: u64,
    size: u64,
    symbol_type: String,
    binding: String,
    section: String,
}

#[derive(Serialize, Clone)]
struct Function {
    name: String,
    address: u64,
    size: u64,
    parameters: Vec<HashMap<String, String>>,
    return_type: String,
}

#[derive(Serialize, Clone)]
struct Field {
    name: String,
    #[serde(rename = "type")]
    field_type: String,
}

struct TypeInfo {
    tag: gimli::DwTag,
    name: String,
    type_offset: Option<usize>, // absolute offset in .debug_info
}

struct Typedef {
    name: String,
    type_offset: Option<usize>,
}

struct CUResult {
    func_params: HashMap<String, Vec<HashMap<String, String>>>,
    structures: HashMap<String, Vec<Field>>,
    struct_by_offset: HashMap<usize, Vec<Field>>,
    global_vars: HashMap<String, String>,
    typedefs: Vec<Typedef>,
}



fn get_die_name(
    dwarf: &gimli::Dwarf<Reader<'_>>,
    unit: &gimli::Unit<Reader<'_>>,
    entry: &gimli::DebuggingInformationEntry<Reader<'_>>
) -> Option<String> {
    if let Some(attr) = entry.attr_value(gimli::DW_AT_name).unwrap_or(None) {
        if let Some(s) = dwarf.attr_string(unit, attr).ok() {
            return Some(s.to_string_lossy().into_owned());
        }
    }
    None
}

fn get_absolute_type_offset(
    unit: &gimli::Unit<Reader<'_>>,
    entry: &gimli::DebuggingInformationEntry<Reader<'_>>
) -> Option<usize> {
    if let Some(attr_val) = entry.attr_value(gimli::DW_AT_type).unwrap_or(None) {
        match attr_val {
            gimli::AttributeValue::UnitRef(offset) => {
                return Some(offset.to_debug_info_offset(&unit.header).unwrap().0);
            }
            gimli::AttributeValue::DebugInfoRef(offset) => {
                return Some(offset.0);
            }
            _ => {}
        }
    }
    None
}

fn resolve_type_name(offset: usize, type_map: &HashMap<usize, TypeInfo>) -> String {
    let mut seen = HashSet::new();
    resolve_type_name_recursive(offset, type_map, &mut seen)
}

fn resolve_type_name_recursive(
    offset: usize,
    type_map: &HashMap<usize, TypeInfo>,
    seen: &mut HashSet<usize>
) -> String {
    if seen.contains(&offset) {
        return "loop".to_string();
    }
    seen.insert(offset);

    let info = match type_map.get(&offset) {
        Some(i) => i,
        None => return "unknown".to_string(),
    };

    let result = match info.tag {
        gimli::DW_TAG_base_type => {
            if info.name.is_empty() {
                "void".to_string()
            } else {
                info.name.clone()
            }
        }
        gimli::DW_TAG_typedef => info.name.clone(),
        gimli::DW_TAG_structure_type => {
            if info.name.is_empty() {
                "struct <anon>".to_string()
            } else {
                format!("struct {}", info.name)
            }
        }
        gimli::DW_TAG_class_type => {
            if info.name.is_empty() {
                "class <anon>".to_string()
            } else {
                info.name.clone()
            }
        }
        gimli::DW_TAG_union_type => {
            if info.name.is_empty() {
                "union <anon>".to_string()
            } else {
                format!("union {}", info.name)
            }
        }
        gimli::DW_TAG_pointer_type => {
            if let Some(type_offset) = info.type_offset {
                format!("{}*", resolve_type_name_recursive(type_offset, type_map, seen))
            } else {
                "void*".to_string()
            }
        }
        gimli::DW_TAG_const_type => {
            if let Some(type_offset) = info.type_offset {
                format!("const {}", resolve_type_name_recursive(type_offset, type_map, seen))
            } else {
                "const void".to_string()
            }
        }
        gimli::DW_TAG_volatile_type => {
            if let Some(type_offset) = info.type_offset {
                format!("volatile {}", resolve_type_name_recursive(type_offset, type_map, seen))
            } else {
                "volatile void".to_string()
            }
        }
        gimli::DW_TAG_array_type => {
            if let Some(type_offset) = info.type_offset {
                format!("{}[]", resolve_type_name_recursive(type_offset, type_map, seen))
            } else {
                "array".to_string()
            }
        }
        _ => {
            if !info.name.is_empty() {
                info.name.clone()
            } else {
                "unknown".to_string()
            }
        }
    };

    seen.remove(&offset);
    result
}

#[pyfunction]
fn compute_md5(py: Python<'_>, elf_path: &str) -> PyResult<String> {
    // Release the GIL while hashing so the caller's other Python threads
    // (e.g. the Qt event loop) keep running during large-file I/O.
    py.allow_threads(|| {
        let file = File::open(elf_path)
            .map_err(|e| pyo3::exceptions::PyFileNotFoundError::new_err(format!("Failed to open ELF file: {}", e)))?;
        let mmap = unsafe { Mmap::map(&file) }
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Failed to memory map ELF file: {}", e)))?;
        let digest = md5::compute(&mmap);
        Ok(format!("{:x}", digest))
    })
}

#[pyfunction]
fn parse_elf(py: Python<'_>, elf_path: &str) -> PyResult<String> {
    // Release the GIL for the whole parse: no Python objects are touched
    // until the JSON string result crosses back over the boundary.
    py.allow_threads(|| parse_elf_impl(elf_path))
}

fn parse_elf_impl(elf_path: &str) -> PyResult<String> {
    let file = File::open(elf_path)
        .map_err(|e| pyo3::exceptions::PyFileNotFoundError::new_err(format!("Failed to open ELF file: {}", e)))?;
    let mmap = unsafe { Mmap::map(&file) }
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Failed to memory map ELF file: {}", e)))?;
    let elf_file = object::File::parse(&*mmap)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Failed to parse ELF headers: {}", e)))?;

    // Compute hexadecimal MD5 hash of the memory-mapped file natively in Rust
    let digest = md5::compute(&mmap);
    let elf_hash = format!("{:x}", digest);

    // 1. Extract symbols
    let mut symbols = Vec::new();
    let mut functions = Vec::new();

    for symbol in elf_file.symbols() {
        let name = match symbol.name() {
            Ok(n) => {
                if n.is_empty() { continue; }
                n.to_string()
            }
            Err(_) => continue,
        };

        let sym_type = match symbol.kind() {
            SymbolKind::Text => "STT_FUNC",
            SymbolKind::Data => "OBJECT",
            SymbolKind::Section => "SECTION",
            SymbolKind::File => "FILE",
            SymbolKind::Label => "NOTYPE",
            _ => "UNKNOWN",
        };

        let binding = if symbol.is_weak() {
            "STB_WEAK"
        } else if symbol.is_global() {
            "STB_GLOBAL"
        } else {
            "STB_LOCAL"
        };

        let section = match symbol.section() {
            object::SymbolSection::Undefined => "UNDEF".to_string(),
            object::SymbolSection::Absolute => "ABS".to_string(),
            object::SymbolSection::Common => "COMMON".to_string(),
            object::SymbolSection::Section(idx) => {
                elf_file.section_by_index(idx)
                    .map(|s| s.name().unwrap_or("UNKNOWN").to_string())
                    .unwrap_or_else(|_| "UNKNOWN".to_string())
            }
            _ => "UNKNOWN".to_string(),
        };

        let address = symbol.address();
        let size = symbol.size();

        symbols.push(Symbol {
            name: name.clone(),
            address,
            size,
            symbol_type: sym_type.to_string(),
            binding: binding.to_string(),
            section,
        });

        if sym_type == "STT_FUNC" {
            let func = Function {
                name: name.clone(),
                address,
                size,
                parameters: Vec::new(),
                return_type: "".to_string(),
            };
            functions.push(func);
        }
    }

    // Relocate all .debug_* sections upfront
    let mut relocated_sections = HashMap::new();
    for section in elf_file.sections() {
        if let Ok(name) = section.name() {
            if name.starts_with(".debug_") {
                let relocated_data = load_and_relocate_section(&elf_file, name);
                relocated_sections.insert(name.to_string(), relocated_data);
            }
        }
    }

    // 2. Extract DWARF info using relocated sections
    let load_section = |id: gimli::SectionId| -> Result<gimli::EndianSlice<'_, gimli::RunTimeEndian>, gimli::Error> {
        let name = id.name();
        let data = match relocated_sections.get(name) {
            Some(data) => &data[..],
            None => {
                match elf_file.section_by_name(name) {
                    Some(ref section) => section.data().unwrap_or(&[]),
                    None => &[],
                }
            }
        };
        Ok(gimli::EndianSlice::new(data, gimli::RunTimeEndian::Little))
    };
    
    // Load DWARF safely. If there is no DWARF info or it's malformed, fall back to empty/default DWARF extraction
    let dwarf = match gimli::Dwarf::load(&load_section) {
        Ok(d) => d,
        Err(_) => {
            let output = serde_json::json!({
                "elf_path": elf_path,
                "elf_hash": elf_hash,
                "symbols": symbols,
                "functions": functions,
                "structures": HashMap::<String, Vec<Field>>::new(),
                "global_vars": HashMap::<String, String>::new(),
            });
            let json_str = serde_json::to_string(&output)
                .map_err(|err| pyo3::exceptions::PyValueError::new_err(err.to_string()))?;
            return Ok(json_str);
        }
    };

    let mut type_map = HashMap::new();
    let mut cu_headers = Vec::new();

    // Pass 1: Build type cache and collect CU headers sequentially
    let mut units = dwarf.units();
    while let Some(header) = units.next().unwrap_or(None) {
        cu_headers.push(header);
        if let Ok(mut unit) = dwarf.unit(header) {
            let mut str_offsets_base = None;
            let mut addr_base = None;
            let mut loclists_base = None;
            let mut rnglists_base = None;
            {
                let mut entries = unit.entries();
                if let Ok(Some((_, entry))) = entries.next_dfs() {
                    if entry.tag() == gimli::DW_TAG_compile_unit {
                        if let Some(gimli::AttributeValue::DebugStrOffsetsBase(base)) = entry.attr_value(gimli::DW_AT_str_offsets_base).unwrap_or(None) {
                            str_offsets_base = Some(base);
                        }
                        if let Some(gimli::AttributeValue::DebugAddrBase(base)) = entry.attr_value(gimli::DW_AT_addr_base).unwrap_or(None) {
                            addr_base = Some(base);
                        }
                        if let Some(gimli::AttributeValue::DebugLocListsBase(base)) = entry.attr_value(gimli::DW_AT_loclists_base).unwrap_or(None) {
                            loclists_base = Some(base);
                        }
                        if let Some(gimli::AttributeValue::DebugRngListsBase(base)) = entry.attr_value(gimli::DW_AT_rnglists_base).unwrap_or(None) {
                            rnglists_base = Some(base);
                        }
                    }
                }
            }
            let header_size = if unit.header.format() == gimli::Format::Dwarf64 { 16 } else { 8 };
            if let Some(base) = str_offsets_base {
                unit.str_offsets_base = base;
            } else {
                unit.str_offsets_base = gimli::DebugStrOffsetsBase(header_size);
            }
            if let Some(base) = addr_base {
                unit.addr_base = base;
            }
            if let Some(base) = loclists_base {
                unit.loclists_base = base;
            }
            if let Some(base) = rnglists_base {
                unit.rnglists_base = base;
            }
            let mut entries = unit.entries();
            while let Ok(Some((_, entry))) = entries.next_dfs() {
                match entry.tag() {
                    gimli::DW_TAG_base_type |
                    gimli::DW_TAG_typedef |
                    gimli::DW_TAG_structure_type |
                    gimli::DW_TAG_class_type |
                    gimli::DW_TAG_union_type |
                    gimli::DW_TAG_pointer_type |
                    gimli::DW_TAG_const_type |
                    gimli::DW_TAG_volatile_type |
                    gimli::DW_TAG_array_type => {
                        let name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                        let type_offset = get_absolute_type_offset(&unit, entry);
                        if let Some(abs_offset) = entry.offset().to_debug_info_offset(&unit.header) {
                            type_map.insert(abs_offset.0, TypeInfo {
                                tag: entry.tag(),
                                name,
                                type_offset,
                            });
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    // Pass 2: Extract details in parallel across CUs using Rayon
    let cu_results: Vec<CUResult> = cu_headers.par_iter().map(|header| {
        let mut unit = match dwarf.unit(*header) {
            Ok(u) => u,
            Err(_) => return CUResult {
                func_params: HashMap::new(),
                structures: HashMap::new(),
                struct_by_offset: HashMap::new(),
                global_vars: HashMap::new(),
                typedefs: Vec::new(),
            }
        };
        let mut str_offsets_base = None;
        let mut addr_base = None;
        let mut loclists_base = None;
        let mut rnglists_base = None;
        {
            let mut entries = unit.entries();
            if let Ok(Some((_, entry))) = entries.next_dfs() {
                if entry.tag() == gimli::DW_TAG_compile_unit {
                    if let Some(gimli::AttributeValue::DebugStrOffsetsBase(base)) = entry.attr_value(gimli::DW_AT_str_offsets_base).unwrap_or(None) {
                        str_offsets_base = Some(base);
                    }
                    if let Some(gimli::AttributeValue::DebugAddrBase(base)) = entry.attr_value(gimli::DW_AT_addr_base).unwrap_or(None) {
                        addr_base = Some(base);
                    }
                    if let Some(gimli::AttributeValue::DebugLocListsBase(base)) = entry.attr_value(gimli::DW_AT_loclists_base).unwrap_or(None) {
                        loclists_base = Some(base);
                    }
                    if let Some(gimli::AttributeValue::DebugRngListsBase(base)) = entry.attr_value(gimli::DW_AT_rnglists_base).unwrap_or(None) {
                        rnglists_base = Some(base);
                    }
                }
            }
        }
        let header_size = if unit.header.format() == gimli::Format::Dwarf64 { 16 } else { 8 };
        if let Some(base) = str_offsets_base {
            unit.str_offsets_base = base;
        } else {
            unit.str_offsets_base = gimli::DebugStrOffsetsBase(header_size);
        }
        if let Some(base) = addr_base {
            unit.addr_base = base;
        }
        if let Some(base) = loclists_base {
            unit.loclists_base = base;
        }
        if let Some(base) = rnglists_base {
            unit.rnglists_base = base;
        }
        let mut entries = unit.entries();
        let mut res = CUResult {
            func_params: HashMap::new(),
            structures: HashMap::new(),
            struct_by_offset: HashMap::new(),
            global_vars: HashMap::new(),
            typedefs: Vec::new(),
        };

        let mut depth = 0;

        // DFS State variables
        let mut current_func_name: Option<String> = None;
        let mut current_func_depth = 0;
        let mut current_func_params = Vec::new();

        let mut current_struct_offset: Option<usize> = None;
        let mut current_struct_name: Option<String> = None;
        let mut current_struct_depth = 0;
        let mut current_struct_fields = Vec::new();

        while let Ok(Some((depth_delta, entry))) = entries.next_dfs() {
            depth += depth_delta;

            // Check state exits first (when depth ascends back to or above parent depth)
            if let Some(ref name) = current_func_name {
                if depth <= current_func_depth {
                    res.func_params.insert(name.clone(), std::mem::take(&mut current_func_params));
                    current_func_name = None;
                }
            }
            if let Some(sd) = current_struct_offset {
                if depth <= current_struct_depth {
                    let fields = std::mem::take(&mut current_struct_fields);
                    res.struct_by_offset.insert(sd, fields.clone());
                    if let Some(ref name) = current_struct_name {
                        res.structures.insert(name.clone(), fields);
                    }
                    current_struct_offset = None;
                    current_struct_name = None;
                }
            }

            // Process based on state
            if current_func_name.is_some() {
                if entry.tag() == gimli::DW_TAG_formal_parameter {
                    let p_name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                    if !p_name.is_empty() {
                        let mut p_type = "unknown".to_string();
                        if let Some(t_offset) = get_absolute_type_offset(&unit, entry) {
                            p_type = resolve_type_name(t_offset, &type_map);
                        }
                        let mut param_map = HashMap::new();
                        param_map.insert("name".to_string(), p_name);
                        param_map.insert("type".to_string(), p_type);
                        current_func_params.push(param_map);
                    }
                }
            } else if current_struct_offset.is_some() {
                if entry.tag() == gimli::DW_TAG_member {
                    let f_name = get_die_name(&dwarf, &unit, entry).unwrap_or_else(|| "<anonymous>".to_string());
                    let mut f_type = "unknown".to_string();
                    if let Some(t_offset) = get_absolute_type_offset(&unit, entry) {
                        f_type = resolve_type_name(t_offset, &type_map);
                    }
                    current_struct_fields.push(Field { name: f_name, field_type: f_type });
                } else if entry.tag() == gimli::DW_TAG_inheritance {
                    let mut f_type = "unknown".to_string();
                    if let Some(t_offset) = get_absolute_type_offset(&unit, entry) {
                        f_type = resolve_type_name(t_offset, &type_map);
                    }
                    current_struct_fields.push(Field { name: "<base>".to_string(), field_type: f_type });
                }
            } else {
                // Neutral state: scan for declarations
                if entry.tag() == gimli::DW_TAG_subprogram {
                    let name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                    if !name.is_empty() {
                        current_func_name = Some(name);
                        current_func_depth = depth;
                        current_func_params.clear();
                    }
                } else if entry.tag() == gimli::DW_TAG_structure_type ||
                           entry.tag() == gimli::DW_TAG_class_type ||
                           entry.tag() == gimli::DW_TAG_union_type {
                    
                    if let Some(gimli::AttributeValue::Flag(true)) = entry.attr_value(gimli::DW_AT_declaration).unwrap_or(None) {
                        continue;
                    }

                    let s_name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                    if let Some(abs_offset) = entry.offset().to_debug_info_offset(&unit.header) {
                        current_struct_offset = Some(abs_offset.0);
                        current_struct_name = if s_name.is_empty() { None } else { Some(s_name) };
                        current_struct_depth = depth;
                        current_struct_fields.clear();
                    }
                } else if entry.tag() == gimli::DW_TAG_typedef {
                    let name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                    let type_offset = get_absolute_type_offset(&unit, entry);
                    if !name.is_empty() && type_offset.is_some() {
                        res.typedefs.push(Typedef { name, type_offset });
                    }
                } else if entry.tag() == gimli::DW_TAG_variable {
                    if depth == 1 {
                        let name = get_die_name(&dwarf, &unit, entry).unwrap_or_default();
                        if !name.is_empty() {
                            let mut v_type = "unknown".to_string();
                            if let Some(t_offset) = get_absolute_type_offset(&unit, entry) {
                                v_type = resolve_type_name(t_offset, &type_map);
                            }
                            res.global_vars.insert(name, v_type);
                        }
                    }
                }
            }
        }

        // Handle EOF exits if we are still parsing a subprogram or struct at the end of the CU
        if let Some(ref name) = current_func_name {
            res.func_params.insert(name.clone(), current_func_params);
        }
        if let Some(sd) = current_struct_offset {
            let fields = current_struct_fields;
            res.struct_by_offset.insert(sd, fields.clone());
            if let Some(ref name) = current_struct_name {
                res.structures.insert(name.clone(), fields);
            }
        }

        res
    }).collect();

    // Merge parallel results
    let mut structures = HashMap::new();
    let mut struct_by_offset = HashMap::new();
    let mut global_vars = HashMap::new();
    let mut typedefs = Vec::new();
    let mut func_params_map = HashMap::new();

    for r in cu_results {
        structures.extend(r.structures);
        struct_by_offset.extend(r.struct_by_offset);
        global_vars.extend(r.global_vars);
        typedefs.extend(r.typedefs);
        func_params_map.extend(r.func_params);
    }

    // Populate function parameters in the sequential output list
    for func in &mut functions {
        if let Some(params) = func_params_map.get(&func.name) {
            func.parameters = params.clone();
        }
    }

    // Typedef resolution pass (Resolving anonymous structures using offsets)
    for td in typedefs {
        let mut curr_offset = td.type_offset;
        let mut seen = HashSet::new();
        loop {
            if let Some(offset) = curr_offset {
                if seen.contains(&offset) { break; }
                seen.insert(offset);

                if let Some(t_info) = type_map.get(&offset) {
                    if t_info.tag == gimli::DW_TAG_const_type ||
                       t_info.tag == gimli::DW_TAG_volatile_type ||
                       t_info.tag == gimli::DW_TAG_typedef {
                        curr_offset = t_info.type_offset;
                    } else if t_info.tag == gimli::DW_TAG_structure_type ||
                              t_info.tag == gimli::DW_TAG_class_type ||
                              t_info.tag == gimli::DW_TAG_union_type {
                        if let Some(fields) = struct_by_offset.get(&offset) {
                            structures.insert(td.name.clone(), fields.clone());
                        }
                        break;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            } else {
                break;
            }
        }
    }

    // Serialize to JSON
    let output = serde_json::json!({
        "elf_path": elf_path,
        "elf_hash": elf_hash,
        "symbols": symbols,
        "functions": functions,
        "structures": structures,
        "global_vars": global_vars,
    });

    let json_str = serde_json::to_string(&output)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Failed to serialize JSON: {}", e)))?;
    Ok(json_str)
}

#[pymodule]
fn rust_elf_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_elf, m)?)?;
    m.add_function(wrap_pyfunction!(compute_md5, m)?)?;
    Ok(())
}

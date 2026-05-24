import json
import os
import hashlib
from PyQt6 import QtWidgets
from core.elf_parser import ELFParser
from dataclasses import asdict
from .Logic_History import HistoryManager

class ProjectSaver:
    """
    Handles saving and loading of the project file (.arch).
    The project file is a JSON wrapper containing:
    1. Table Data (Configuration, Settings, Rows)
    2. ELF Data (Cache of the loaded ELF/JSON)
    """

    @staticmethod
    def compute_integrity_hash(project_path: str) -> str:
        hasher = hashlib.sha256()
        
        files_to_hash = []
        for root, dirs, files in os.walk(project_path):
            for file in files:
                # Exclude .lock and .integrity
                if file in (".lock", ".integrity"):
                    continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, project_path)
                files_to_hash.append((rel_path, abs_path))
                
        # Sort alphabetically by relative path for determinism
        files_to_hash.sort(key=lambda x: x[0])
        
        for rel_path, abs_path in files_to_hash:
            try:
                with open(abs_path, 'rb') as f:
                    hasher.update(f.read())
            except Exception:
                pass
                
        return hasher.hexdigest()

    @staticmethod
    def get_temp_path(file_path):
        """
        Returns the path for the temporary dirty file: .tmp_<filename>
        """
        if not file_path:
            return None
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return os.path.join(directory, f".tmp_{filename}")

    @staticmethod
    def save_temp(main_window, original_path):
        """
        Saves the current state to a hidden temporary file to mark as dirty.
        """
        if not original_path:
            return False, "No project file."
        
        temp_path = ProjectSaver.get_temp_path(original_path)
        return ProjectSaver.save_project(main_window, temp_path, is_temp=True)

    @staticmethod
    def has_temp_changes(original_path):
        """
        Checks if a temporary file exists for the given project path.
        """
        if not original_path:
            return False
        temp_path = ProjectSaver.get_temp_path(original_path)
        return os.path.exists(temp_path)

    @staticmethod
    def cleanup_temp(original_path):
        """
        Removes the temporary file or directory if it exists.
        """
        if not original_path:
            return
        temp_path = ProjectSaver.get_temp_path(original_path)
        if os.path.exists(temp_path):
            try:
                if os.path.isdir(temp_path):
                    import shutil
                    shutil.rmtree(temp_path)
                else:
                    os.remove(temp_path)
            except OSError:
                pass # Best effort

    # Cache for ELF serialization to avoid re-processing 200k+ symbols on every auto-save
    _cached_elf_data = None
    _cached_parser_hash = None

    @staticmethod
    def save_project(main_window, path, is_temp=False):
        if not getattr(main_window, 'edit_mode', True):
            return False, "Saving is disabled in View-Only mode."
        try:
            # Handle Path: If it refers to an existing FILE, we must remove it to create a directory
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError as e:
                    return False, f"Cannot overwrite existing file with project directory: {e}"
            
            # Create Directory
            os.makedirs(path, exist_ok=True)
            
            # 1. Collect Data
            full_table_data = main_window.arch_controller.get_project_data()
            layout_data = full_table_data.get("config", [])
            settings_data = full_table_data.get("settings", {})
            rows_data = full_table_data.get("rows", [])
            
            # 2. Collect ELF Data
            elf_data = {}
            if main_window.parser:
                # Check Cache
                current_hash = main_window.parser.md5_hash
                if (ProjectSaver._cached_elf_data is not None and 
                    ProjectSaver._cached_parser_hash == current_hash):
                    elf_data = ProjectSaver._cached_elf_data
                else:
                    elf_data = {
                        "elf_path": str(main_window.parser.elf_path) if main_window.parser.elf_path else "",
                        "elf_hash": main_window.parser.md5_hash,
                        "symbols": [asdict(s) for s in main_window.parser.symbols],
                        "functions": [{
                            'name': f.name,
                            'address': f.address,
                            'size': f.size,
                            'parameters': f.parameters,
                            'return_type': f.return_type
                        } for f in main_window.parser.functions],
                        "structures": main_window.parser.structures,
                        "global_vars": main_window.parser.global_vars_dwarf
                    }
                    ProjectSaver._cached_elf_data = elf_data
                    ProjectSaver._cached_parser_hash = current_hash

            # 3. Save Files
            
            # layout.json (Configuration & Settings)
            test_case_json = {}
            if hasattr(main_window, 'test_case_controller'):
                test_case_json = {
                    "project_title": main_window.test_case_controller.get_project_title(),
                    "design_template": main_window.test_case_controller.get_design_template()
                }

            # Update settings_data with auto_save_interval
            settings_data["auto_save_interval"] = getattr(main_window, 'auto_save_interval', 'immediate')

            layout_json = {
                "version": "2.0",
                "layout": layout_data,
                "settings": settings_data,
                "test_case_design": test_case_json
            }
            master_hash = getattr(main_window, 'master_password_hash', None)
            if master_hash:
                layout_json["master_password_hash"] = master_hash

            with open(os.path.join(path, "layout.json"), 'w') as f:
                json.dump(layout_json, f, indent=4)
                
            # database.json (ELF Cache) -> REMOVED
            # User Req: "Release JSON is currently saved as Database.JSON -> It should be saved in the SW Release folder"
            # We now save this inside the Release Model (Step 5 below).
            
            # Cleanup old database.json if exists
            db_path = os.path.join(path, "database.json")
            if os.path.exists(db_path):
                 try: os.remove(db_path)
                 except: pass

            # 4. Architecture Models (New System)
            main_window.arch_controller.flush_current_data_to_model()

            if not is_temp:
                # Update controller with path (this triggers manager to update paths)
                main_window.arch_controller.set_project_path(path)
                main_window.arch_controller.model_manager.save_registry()

                # 5. Save Table & ELF Data into Active Release
                active_release = main_window.arch_controller.release_manager.get_active_release()
                if active_release:
                    if elf_data:
                        if active_release.data_cache is None:
                            active_release.data_cache = {}
                        active_release.data_cache["database"] = elf_data
                        if not active_release.elf_hash and "elf_hash" in elf_data:
                            active_release.elf_hash = elf_data["elf_hash"]
                    if active_release.data_cache:
                        main_window.arch_controller.release_manager._save_data(active_release, active_release.data_cache)

                # Save ALL models to disk (needed for Save As / first save path migration)
                for model in main_window.arch_controller.model_manager.models:
                    if model.data_cache and model.file_path:
                        try:
                            with open(model.file_path, 'w') as f:
                                json.dump(model.data_cache, f, indent=4)
                        except Exception as e:
                            print(f"Failed to auto-save model {model.name}: {e}")
            
            # Legacy: Remove table_data.json if it exists to avoid confusion, or keep as backup?
            # Let's clean it up to enforce new structure.
            legacy_data_path = os.path.join(path, "table_data.json")
            if os.path.exists(legacy_data_path):
                 try:
                     os.remove(legacy_data_path)
                 except: pass # Ignore

            # Save History if not is_temp
            if not is_temp:
                if not hasattr(main_window, 'history_manager') or not main_window.history_manager:
                    main_window.history_manager = HistoryManager(path)
                else:
                    main_window.history_manager.project_path = path
                main_window.history_manager.save_history()

            # Cleanup temp if needed
            if not is_temp:
                 ProjectSaver.cleanup_temp(path)
                 
                 # Save integrity hash (Feature 3)
                 integrity_hash = ProjectSaver.compute_integrity_hash(path)
                 with open(os.path.join(path, ".integrity"), 'w') as f:
                     f.write(integrity_hash)
                 
            return True, "Project saved successfully." + (" (Temp)" if is_temp else "")

        except Exception as e:
            return False, f"Failed to save project: {str(e)}"

    @staticmethod
    def load_project(main_window, path):
        try:
            # Set is_loading flag and call reset_controller
            main_window.arch_controller.is_loading = True
            main_window.arch_controller.reset_controller()

            # Integrity check (Feature 3)
            integrity_mismatch = False
            integrity_file = os.path.join(path, ".integrity")
            if os.path.exists(integrity_file):
                with open(integrity_file, 'r') as f:
                    stored_hash = f.read().strip()
                computed_hash = ProjectSaver.compute_integrity_hash(path)
                if computed_hash != stored_hash:
                    integrity_mismatch = True
            else:
                # If there's no .integrity file, but layout.json exists, it means it's a legacy or tampered project
                if os.path.exists(os.path.join(path, "layout.json")):
                    integrity_mismatch = True
            
            main_window.integrity_mismatch = integrity_mismatch

            # Initialize HistoryManager and load history (Feature 5)
            main_window.history_manager = HistoryManager(path)

            # Enforce Directory Format
            if os.path.isdir(path):
                success, msg = ProjectSaver._load_directory_project(main_window, path)
                main_window.arch_controller.is_loading = False
                return success, msg
            else:
                main_window.arch_controller.is_loading = False
                return False, "Selected path is not a valid project directory."

        except Exception as e:
            if hasattr(main_window, 'arch_controller'):
                main_window.arch_controller.is_loading = False
            return False, f"Failed to load project: {str(e)}"

    @staticmethod
    def _load_directory_project(main_window, dir_path):
        try:
            # 1. Load Database (ELF) -> MOVED to Step 3 (Release Load)
            # Old database.json support (Legacy Migration?)
            # If database.json exists but no releases, maybe keep it?
            # But new logic relies on Release. 
            pass

            # 2. Load Layout & Settings
            layout_path = os.path.join(dir_path, "layout.json")
            layout_config = []
            settings_config = {}
            test_case_data = {}
            if os.path.exists(layout_path):
                with open(layout_path, 'r') as f:
                    layout_json = json.load(f)
                layout_config = layout_json.get("layout", [])
                settings_config = layout_json.get("settings", {})
                test_case_data = layout_json.get("test_case_design", {})

            # 3. Load Architecture Models (Now Releases)
            # First, set the path so the manager activates (do not flush)
            main_window.arch_controller.set_project_path(dir_path, flush=False)
            
            # CRITICAL: We must explicit LOAD the registry from disk
            mgr = main_window.arch_controller.model_manager
            mgr.load_registry()
            
            # Refresh the UI List Model
            main_window.arch_controller.list_model.refresh()
            
            # Pre-load all models into RAM
            mgr.preload_all_models()
            
            # LOAD ACTIVE RELEASE & ELF DATA
            rel_mgr = main_window.arch_controller.release_manager
            rel_mgr.load_registry()
            
            # Set active release (triggers load from JSON)
            active_release = rel_mgr.get_active_release()
            
            # If we have an active release, populate parser from it
            if active_release:
                 # Ensure data is loaded
                 if active_release.data_cache is None:
                      active_release.data_cache = rel_mgr._load_data(active_release)
                       
                 if active_release.data_cache:
                      if active_release.is_baseline:
                           # Baseline release data cache is table_data.json.
                           # We also read layout.json from baseline folder.
                           baseline_dir = os.path.dirname(active_release.file_path)
                           layout_path = os.path.join(baseline_dir, "layout.json")
                           
                           layout_config = []
                           settings_config = {}
                           if os.path.exists(layout_path):
                               with open(layout_path, 'r') as f:
                                   layout_json = json.load(f)
                               layout_config = layout_json.get("layout", [])
                               settings_config = layout_json.get("settings", {})
                               test_case_data = layout_json.get("test_case_design", {})
                               
                           data_to_load = {
                               "config": layout_config,
                               "settings": settings_config,
                               "rows": active_release.data_cache.get("rows", [])
                           }
                           main_window.arch_controller.load_project_data(data_to_load)
                           
                           if test_case_data and hasattr(main_window, 'test_case_controller'):
                               main_window.test_case_controller.load_data(test_case_data)
                               
                           elf_data = active_release.data_cache.get("database", {})
                      else:
                           elf_data = active_release.data_cache.get("database", {})

                      if elf_data:
                           print(f"Loading ELF Data from Release: {active_release.name}")
                           ProjectSaver._populate_parser(main_window, elf_data)
            else:
                 # Attempt legacy database.json load if no active release?
                 db_path = os.path.join(dir_path, "database.json")
                 if os.path.exists(db_path):
                     print("Loading legacy database.json...")
                     with open(db_path, 'r') as f:
                        db_json = json.load(f)
                     elf_data = db_json.get("database", {})
                     ProjectSaver._populate_parser(main_window, elf_data)
            
            # 4. Legacy Migration Check
            # If manager has NO releases AND table_data.json exists,
            # it means we are loading a legacy project. We should import the rows into a default release.
            data_path = os.path.join(dir_path, "table_data.json")
            
            if not mgr.models and os.path.exists(data_path):
                 print("Detected Legacy Project. Migrating to Architecture Manager...")
                 try:
                     with open(data_path, 'r') as f:
                         data_json = json.load(f)
                     rows_config = data_json.get("rows", [])
                     
                     # Create a default model
                     new_model = mgr.create_model("Legacy_Migration", "In Work")
                     new_model.data_cache = {"rows": rows_config}
                     
                     # Save it immediately
                     # ArchitectureManager doesn't have _save_data, manually save
                     if new_model.file_path:
                         with open(new_model.file_path, 'w') as f:
                             json.dump(new_model.data_cache, f, indent=4)
                             
                     mgr.set_active_model(0)
                     
                     print("Legacy Migration Successful.")
                 except Exception as e:
                     print(f"Legacy Migration Failed: {e}")
            
            # 5. Load Active Release into Table
            main_window.arch_controller.load_active_model_to_table()
            
            # 6. Apply Settings (from layout.json)
            # We construct a partial data dict to pass to load_project_data for settings only
            # Need to update controller's settings from file BEFORE loading model rows if possible
            main_window.arch_controller.active_config = [tuple(c) for c in layout_config]
            main_window.arch_controller._rebuild_column_objects()
            main_window.arch_controller.current_default_cyclicity = settings_config.get("default_cyclicity", "10")
            main_window.arch_controller.show_retired = settings_config.get("show_retired", True)
            main_window.arch_controller.show_deleted = settings_config.get("show_deleted", False)
            main_window.arch_controller._setup_table_style()
            
            # Now reload rows from model (which uses the new column config)
            main_window.arch_controller.load_active_model_to_table()

            # 7. Load Test Case Design template
            if test_case_data and hasattr(main_window, 'test_case_controller'):
                main_window.test_case_controller.load_data(test_case_data)
            
            return True, "Project loaded successfully."
            
        except Exception as e:
             return False, f"Failed to load directory project: {e}"

    @staticmethod
    def _populate_parser(main_window, elf_data):
        from core.elf_parser import ELFParser, Symbol, Function
        from pathlib import Path
        
        parser = ELFParser()
        parser.elf_path = Path(elf_data.get("elf_path", ""))
        parser.md5_hash = elf_data.get("elf_hash")
        
        parser.symbols = [Symbol(**s) for s in elf_data.get("symbols", [])]
        parser.functions = [Function(**f) for f in elf_data.get("functions", [])]
        parser.structures = elf_data.get("structures", {})
        parser.global_vars_dwarf = elf_data.get("global_vars", {})
        
        parser._build_function_address_map()
        
        main_window.parser = parser
        main_window.arch_controller.populate_from_parser(parser)
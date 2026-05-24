from dataclasses import dataclass, field
import json
import os
import shutil
import datetime
from typing import List, Optional, Dict
from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice
from PyQt6.QtGui import QColor, QFont

@dataclass
class ReleaseModel:
    name: str
    file_path: Optional[str] # Absolute path to the JSON file
    is_baseline: bool = False
    parent_release_name: Optional[str] = None # If this is a baseline, which release did it come from?
    data_cache: Optional[dict] = None # Cache for in-memory operations
    description: str = ""
    timestamp: str = "" # Creation timestamp
    elf_path: Optional[str] = None # Path to the ELF file associated with this release
    elf_hash: Optional[str] = None # Unique MD5 hash of the ELF/JSON database
    is_deleted: bool = False
    deletion_comment: str = ""
    
    def to_dict(self, project_root=None):
        """
        Serializes the model. Stores paths relative to project root if provided.
        """
        rel_path = self.file_path
        if project_root and self.file_path and self.file_path.startswith(project_root):
            rel_path = os.path.relpath(self.file_path, project_root)
            
        return {
            "name": self.name,
            "file_path": rel_path,
            "is_baseline": self.is_baseline,
            "parent_release_name": self.parent_release_name,
            "description": self.description,
            "timestamp": self.timestamp,
            "elf_path": self.elf_path,
            "elf_hash": self.elf_hash,
            "is_deleted": self.is_deleted,
            "deletion_comment": self.deletion_comment
        }

    @staticmethod
    def from_dict(data, project_root=None):
        path = data.get("file_path")
        if project_root and path and not os.path.isabs(path):
            path = os.path.join(project_root, path)
            
        return ReleaseModel(
            name=data["name"],
            file_path=path,
            is_baseline=data.get("is_baseline", False),
            parent_release_name=data.get("parent_release_name"),
            description=data.get("description", ""),
            timestamp=data.get("timestamp", ""),
            elf_path=data.get("elf_path"),
            elf_hash=data.get("elf_hash"),
            is_deleted=data.get("is_deleted", False),
            deletion_comment=data.get("deletion_comment", "")
        )

class ReleaseManager:
    """
    Manages Software Releases and Baselines.
    Replaces the functionality of ArchitectureManager for the new workflow.
    """
    def __init__(self, project_path=None):
        self.project_path = project_path
        self.releases: List[ReleaseModel] = []
        self.active_release_index = -1
        
        # Paths
        self.releases_dir = "sw_releases"
        self.baselines_dir = "Baselines"

        if self.project_path:
            self._ensure_directories()
            self.load_registry()

    def set_project_path(self, new_path):
        old_path = self.project_path
        self.project_path = new_path
        if new_path:
            self._ensure_directories()
            
            # Smart Save/Load
            if self.releases:
                # We have in-memory releases, save/migrate them to the correct path
                for r in self.releases:
                    old_file_path = r.file_path
                    if not r.file_path:
                        filename = f"{r.name.replace(' ', '_')}.json"
                        r.file_path = os.path.join(self.project_path, self.releases_dir, filename)
                        
                        counter = 1
                        base_path = r.file_path
                        while os.path.exists(r.file_path):
                             name_part, ext = os.path.splitext(base_path)
                             r.file_path = f"{name_part}_{counter}{ext}"
                             counter += 1
                    elif old_path and new_path != old_path:
                        try:
                            # Re-root the path to the new project path if it was inside the old project path
                            abs_old_path = os.path.abspath(old_path)
                            abs_old_file_path = os.path.abspath(old_file_path)
                            if abs_old_file_path.startswith(abs_old_path):
                                rel_p = os.path.relpath(abs_old_file_path, abs_old_path)
                                r.file_path = os.path.join(new_path, rel_p)
                        except Exception as e:
                            print(f"Error re-rooting release path: {e}")
                    
                    # Ensure parent directory for r.file_path exists
                    if r.file_path:
                        os.makedirs(os.path.dirname(r.file_path), exist_ok=True)
                    
                    if r.data_cache:
                        self._save_data(r, r.data_cache)
                    elif old_file_path and os.path.exists(old_file_path) and old_path and new_path != old_path:
                        try:
                            shutil.copy2(old_file_path, r.file_path)
                        except Exception as e:
                            print(f"Error copying release file from {old_file_path} to {r.file_path}: {e}")
                        
                self.save_registry()
            else:
                # We have no releases (Load Project scenario), try to load from disk
                if os.path.exists(os.path.join(self.project_path, "releases_registry.json")):
                    self.load_registry()

    def _ensure_directories(self):
        if not self.project_path:
            return
        
        os.makedirs(os.path.join(self.project_path, self.releases_dir), exist_ok=True)
        os.makedirs(os.path.join(self.project_path, self.baselines_dir), exist_ok=True)

    def load_registry(self):
        if not self.project_path:
            return

        registry_path = os.path.join(self.project_path, "releases_registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r') as f:
                    data = json.load(f)
                    self.releases = [ReleaseModel.from_dict(r, self.project_path) for r in data.get("releases", [])]
                    
                    active_name = data.get("active_release_name")
                    self.active_release_index = -1
                    if active_name:
                        for i, r in enumerate(self.releases):
                            if r.name == active_name:
                                self.active_release_index = i
                                break
            except Exception as e:
                print(f"Error loading releases registry: {e}")
        else:
            self.releases = []

    def save_registry(self):
        if not self.project_path:
            return

        registry_path = os.path.join(self.project_path, "releases_registry.json")
        
        active_name = None
        if 0 <= self.active_release_index < len(self.releases):
            active_name = self.releases[self.active_release_index].name

        data = {
            "releases": [r.to_dict(self.project_path) for r in self.releases],
            "active_release_name": active_name
        }
        
        try:
            with open(registry_path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving releases registry: {e}")

    def create_release(self, name, description="", copy_from_active=False, elf_path=None, elf_hash=None, elf_data=None):
        """Creates a new Software Release."""
        # Validation: Name must be unique among ALL releases
        if any(r.name == name for r in self.releases):
            raise ValueError(f"Release '{name}' already exists.")

        file_path = None
        
        if self.project_path:
            filename = f"{name.replace(' ', '_')}.json"
            file_path = os.path.join(self.project_path, self.releases_dir, filename)
            
            # Ensure unique filename
            counter = 1
            base_path = file_path
            while os.path.exists(file_path):
                 name_part, ext = os.path.splitext(base_path)
                 file_path = f"{name_part}_{counter}{ext}"
                 counter += 1

        new_release = ReleaseModel(
            name=name,
            file_path=file_path,
            is_baseline=False,
            description=description,
            timestamp=datetime.datetime.now().isoformat(),
            elf_path=elf_path,
            elf_hash=elf_hash
        )
        
        # Initialize Data
        data = {"rows": []}
        if copy_from_active:
            active = self.get_active_release()
            if active:
                data = self._load_data(active)
        
        if elf_data:
            data["database"] = elf_data
        
        new_release.data_cache = data
        self._save_data(new_release, data)
        
        self.releases.insert(0, new_release) # Add to top (newest first)
        self.active_release_index = 0 # Verify if we should auto-switch? Usually yes for "Create New"
        self.save_registry()
        
        return new_release

    def create_baseline(self, release_index, baseline_name, layout_data=None, active_model_data=None):
        """
        Creates a snapshot of the specified release.
        Stores it in the Baselines/[baseline_name]/ folder.
        """
        if not self.project_path:
            raise ValueError("No active project path.")
            
        if not baseline_name or not baseline_name.strip():
            raise ValueError("Baseline name cannot be empty.")
            
        baseline_name = baseline_name.strip()
        
        # Validation: Name must be unique among ALL active releases/baselines
        if any(r.name == baseline_name and not r.is_deleted for r in self.releases):
            raise ValueError(f"A release or baseline named '{baseline_name}' already exists.")

        if not (0 <= release_index < len(self.releases)):
            raise ValueError("Invalid release index")
            
        src_release = self.releases[release_index]
        if src_release.is_baseline:
             raise ValueError("Cannot create a baseline from a baseline.")
             
        baseline_dir = os.path.join(self.project_path, self.baselines_dir, baseline_name)
        # Ensure unique baseline folder name in the file system (to prevent overwriting soft-deleted baselines)
        counter = 1
        base_dir = baseline_dir
        while os.path.exists(baseline_dir):
            baseline_dir = f"{base_dir}_{counter}"
            counter += 1
        os.makedirs(baseline_dir, exist_ok=True)
        
        # File paths inside baseline dir
        table_data_path = os.path.join(baseline_dir, "table_data.json")
        layout_path = os.path.join(baseline_dir, "layout.json")
        metrics_path = os.path.join(baseline_dir, "metrics.json")
        
        # Load ELF parser database from the source release
        src_data = self._load_data(src_release)
        
        if active_model_data is None:
            active_model_data = {}
            
        # Assemble frozen baseline table data (incorporating rows, results, and database)
        table_data = {
            "rows": active_model_data.get("rows", []),
            "column_metadata": active_model_data.get("column_metadata", {}),
            "release_results": active_model_data.get("release_results", {}),
            "database": src_data
        }
        
        # Save files inside baseline dir
        with open(table_data_path, 'w') as f:
            json.dump(table_data, f, indent=4)
            
        if layout_data is None:
            layout_data = {}
        with open(layout_path, 'w') as f:
            json.dump(layout_data, f, indent=4)

        # Copy all active models and their registry for robust multi-model baseline support
        src_registry = os.path.join(self.project_path, "architecture_models_registry.json")
        if os.path.exists(src_registry):
            try:
                with open(src_registry, 'r') as f:
                    registry_data = json.load(f)
                
                # Filter out deleted models
                active_models = [m for m in registry_data.get("models", []) if not m.get("is_deleted", False)]
                
                # Copy active models' JSON files
                for model_info in active_models:
                    filename = model_info.get("filename")
                    if filename:
                        src_model_path = os.path.join(self.project_path, filename)
                        dst_model_path = os.path.join(baseline_dir, filename)
                        if os.path.exists(src_model_path):
                            shutil.copy2(src_model_path, dst_model_path)
                
                # Save filtered registry copy
                registry_data["models"] = active_models
                dst_registry = os.path.join(baseline_dir, "architecture_models_registry.json")
                with open(dst_registry, 'w') as f:
                    json.dump(registry_data, f, indent=4)
            except Exception as e:
                print(f"Warning: Failed to copy multi-model registry to baseline: {e}")
            
        metrics_data = {
            "TODO": "Metrics dashboard features are not yet implemented. This file will store the generated metrics dashboard data for this release.",
            "metrics": {}
        }
        with open(metrics_path, 'w') as f:
            json.dump(metrics_data, f, indent=4)
        
        new_baseline = ReleaseModel(
            name=baseline_name,
            file_path=table_data_path,
            is_baseline=True,
            parent_release_name=src_release.name,
            description=f"Snapshot of {src_release.name}",
            timestamp=datetime.datetime.now().isoformat(),
            data_cache=table_data,
            elf_path=src_release.elf_path,
            elf_hash=src_release.elf_hash
        )
        
        # Baselines usually added to list? User said: "In the release selection window... option to create a baseline"
        # "12. If a release is baselined it should be clearly marked in relesae view"
        # "13. There should be the ability to load a baseline"
        self.releases.append(new_baseline)
        self.save_registry()
        
        return new_baseline

    def rename_release(self, index, new_name):
        if not (0 <= index < len(self.releases)):
            return False, "Invalid index"
            
        model = self.releases[index]
        if model.is_baseline:
            return False, "Cannot rename baselines" # Requirement 7.7/7.8 implies strictness, assuming baselines are immutable artifacts
            
        if any(r.name == new_name for r in self.releases if r is not model):
             return False, "Name already exists"
             
        model.name = new_name
        self.save_registry()
        return True, "Success"

    def delete_release(self, index, deletion_comment=""):
        if not (0 <= index < len(self.releases)):
            return False, "Invalid index"
            
        model = self.releases[index]
        
        # Check if any active baseline points to this
        if not model.is_baseline:
            has_baseline = any(r.is_baseline and not r.is_deleted and r.parent_release_name == model.name for r in self.releases)
            if has_baseline:
                return False, "Cannot delete release that has active baselines."
        
        if model.is_baseline:
            # Soft delete baseline
            model.is_deleted = True
            model.deletion_comment = deletion_comment
            self.save_registry()
            return True, "Soft-deleted"
            
        # Permanent delete normal release
        if model.file_path and os.path.exists(model.file_path):
            try:
                os.remove(model.file_path)
            except Exception as e:
                print(f"Warning: Could not delete entry file: {e}")
                
        self.releases.pop(index)
        
        # Adjust active index
        if self.active_release_index == index:
            self.active_release_index = -1 # None active
        elif self.active_release_index > index:
            self.active_release_index -= 1
            
        self.save_registry()
        return True, "Deleted"

    def get_active_release(self):
        if 0 <= self.active_release_index < len(self.releases):
            return self.releases[self.active_release_index]
        return None

    def set_active_release(self, index):
        if 0 <= index < len(self.releases):
            # Unload previous active release to save memory
            if self.active_release_index != -1 and self.active_release_index != index:
                 prev_release = self.releases[self.active_release_index]
                 prev_release.data_cache = None # Unload from RAM
                 
            self.active_release_index = index
            self.save_registry()
            
            # Load new active release
            new_release = self.releases[index]
            if new_release.data_cache is None:
                new_release.data_cache = self._load_data(new_release)
                
            return new_release
        return None

    def _load_data(self, release: ReleaseModel):
        """Helper to load data from disk or cache."""
        # Pre-load all models into RAM -- REMOVED
        # User Requirement: "Changing between different Software Releases should unload the currently loaded JSON from the memory and loading the new JSON file"
        # We do NOT preload all releases anymore because they now contain heavy ELF data.
        # mgr.preload_all_models() -- Wait, this was ArchitectureManager. ReleaseManager had preload_all_releases.
        if release.data_cache:
            return release.data_cache
        
        if release.file_path and os.path.exists(release.file_path):
            try:
                with open(release.file_path, 'r') as f:
                    data = json.load(f)
                    release.data_cache = data
                    return data
            except Exception as e:
                print(f"Error loading release data: {e}")
        return {"rows": []}

    def _save_data(self, release: ReleaseModel, data):
        """Helper to save data to disk."""
        if not release.file_path:
             return
        
        try:
             with open(release.file_path, 'w') as f:
                 json.dump(data, f, indent=4)
             release.data_cache = data
        except Exception as e:
             print (f"Error saving data: {e}")

    def flush_active_release_data(self):
        """
        Force save the currently active release from cache to disk.
        """
        active = self.get_active_release()
        if active and active.data_cache:
            self._save_data(active, active.data_cache)

    def preload_all_releases(self):
        """
        DEPRECATED/REMOVED: Releases are now lazy-loaded.
        """
        pass

    def move_release(self, old_index, new_index):
        if 0 <= old_index < len(self.releases) and 0 <= new_index < len(self.releases):
            item = self.releases.pop(old_index)
            self.releases.insert(new_index, item)
            
            if self.active_release_index == old_index:
                self.active_release_index = new_index
            elif old_index < self.active_release_index <= new_index:
                self.active_release_index -= 1
            elif new_index <= self.active_release_index < old_index:
                self.active_release_index += 1
                
            self.save_registry()
            return True
        return False

class ReleaseListModel(QAbstractListModel):
    """
    Qt Model to bridge ReleaseManager data to QListView/QListWidget
    """
    ModelRole = Qt.ItemDataRole.UserRole + 1
    
    def __init__(self, manager: ReleaseManager):
        super().__init__()
        self.manager = manager
    
    def rowCount(self, parent=QModelIndex()):
        return len(self.manager.releases)

    def data(self, index, role):
        if not index.isValid():
            return None
        
        if index.row() >= len(self.manager.releases):
            return None
            
        release = self.manager.releases[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            name = release.name
            if release.is_baseline:
                name += " [BASELINE]"
            return name
            
        elif role == Qt.ItemDataRole.BackgroundRole:
            # Color indicator
            if release.is_baseline:
                return QColor("#d3d3d3") # Grey
            elif index.row() == self.manager.active_release_index:
                return QColor("#2a82da") # Active Color? No, foreground usually.
                # Let's keep background simple or use status colors if we had them.
                
        elif role == Qt.ItemDataRole.ForegroundRole:
            if index.row() == self.manager.active_release_index:
                return QColor("white")
            
        elif role == Qt.ItemDataRole.FontRole:
            if index.row() == self.manager.active_release_index:
                 font = QFont()
                 font.setBold(True)
                 return font
                
        elif role == self.ModelRole:
            return release
            
        return None

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    # --- Drag and Drop Support ---
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def flags(self, index):
        default_flags = super().flags(index)
        if index.isValid():
             return default_flags | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        else:
             return default_flags | Qt.ItemFlag.ItemIsDropEnabled

    def mimeTypes(self):
        return ['application/vnd.text.list']

    def mimeData(self, indexes):
        mime = QMimeData()
        encoded_data = QByteArray()
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.WriteOnly)
        
        for index in indexes:
            if index.isValid():
                stream.writeInt32(index.row())
        
        mime.setData('application/vnd.text.list', encoded_data)
        return mime

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat('application/vnd.text.list'):
            return False
            
        if column > 0:
            return False
            
        encoded_data = data.data('application/vnd.text.list')
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.ReadOnly)
        
        src_row = stream.readInt32()
        
        if row == -1:
            if parent.isValid():
                row = parent.row()
            else:
                row = self.rowCount()
        
        if row > src_row:
            row -= 1
            
        if self.manager.move_release(src_row, row):
             self.refresh()
             return True
             
        return False

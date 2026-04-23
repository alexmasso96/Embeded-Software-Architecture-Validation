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
            "elf_path": self.elf_path
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
            elf_path=data.get("elf_path")
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
        self.project_path = new_path
        if new_path:
            self._ensure_directories()
            
            # Smart Save/Load
            if self.releases:
                # We have in-memory releases (New Project scenario), save them to correct path
                for r in self.releases:
                    if not r.file_path:
                        filename = f"{r.name.replace(' ', '_')}.json"
                        r.file_path = os.path.join(self.project_path, self.releases_dir, filename)
                        
                        counter = 1
                        base_path = r.file_path
                        while os.path.exists(r.file_path):
                             name_part, ext = os.path.splitext(base_path)
                             r.file_path = f"{name_part}_{counter}{ext}"
                             counter += 1
                    
                    if r.data_cache:
                        self._save_data(r, r.data_cache)
                        
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

    def create_release(self, name, description="", copy_from_active=False, elf_path=None):
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
            elf_path=elf_path
        )
        
        # Initialize Data
        data = {"rows": []}
        if copy_from_active:
            active = self.get_active_release()
            if active:
                data = self._load_data(active)
        
        new_release.data_cache = data
        self._save_data(new_release, data)
        
        self.releases.insert(0, new_release) # Add to top (newest first)
        self.active_release_index = 0 # Verify if we should auto-switch? Usually yes for "Create New"
        self.save_registry()
        
        return new_release

    def create_baseline(self, release_index):
        """
        Creates a snapshot of the specified release.
        Stores it in the Baselines folder.
        """
        if not (0 <= release_index < len(self.releases)):
            raise ValueError("Invalid release index")
            
        src_release = self.releases[release_index]
        if src_release.is_baseline:
             raise ValueError("Cannot create a baseline from a baseline.")
             
        # Generate Baseline Name
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        baseline_name = f"{src_release.name}_Baseline_{timestamp}"
        
        filename = f"{baseline_name}.json"
        file_path = os.path.join(self.project_path, self.baselines_dir, filename)
        
        # Copy Data
        data = self._load_data(src_release)
        
        new_baseline = ReleaseModel(
            name=baseline_name,
            file_path=file_path,
            is_baseline=True,
            parent_release_name=src_release.name,
            description=f"Snapshot of {src_release.name}",
            timestamp=datetime.datetime.now().isoformat(),
            data_cache=data
        )
        
        self._save_data(new_baseline, data)
        
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

    def delete_release(self, index):
        if not (0 <= index < len(self.releases)):
            return False
            
        model = self.releases[index]
        
        # "3.1 The behavior should be inhibited if for that specific software release a result baseline was created"
        # Check if any baseline points to this
        if not model.is_baseline:
            has_baseline = any(r.is_baseline and r.parent_release_name == model.name for r in self.releases)
            if has_baseline:
                return False, "Cannot delete release that has baselines."
        
        # Delete file
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
                return QColor("white") if role == Qt.ItemDataRole.BackgroundRole and False else QColor("#2a82da")
            
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

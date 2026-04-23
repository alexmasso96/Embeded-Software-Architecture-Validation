from dataclasses import dataclass, field
import json
import os
import copy
from typing import List, Optional
from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex, pyqtSignal, QMimeData, QByteArray, QDataStream, QIODevice
from PyQt6.QtGui import QColor, QFont
from PyQt6 import QtGui

@dataclass
class ArchitectureModel:
    name: str
    file_path: Optional[str] # Can be None if in-memory only (unsaved project)
    status: str = "In Work"  # "Released", "In Work", "Retired"
    is_deleted: bool = False
    data_cache: Optional[dict] = None # Cache for in-memory operations
    
    def to_dict(self):
        # We store the basename of the file to be portable
        fname = os.path.basename(self.file_path) if self.file_path else f"{self.name}.json"
        return {
            "name": self.name,
            "filename": fname,
            "status": self.status,
            "is_deleted": self.is_deleted
        }

    @staticmethod
    def from_dict(data, project_path):
        filename = data.get("filename")
        if not filename:
             # Legacy or error
             filename = f"{data['name']}.json"
             
        file_path = os.path.join(project_path, filename) if project_path else None
        
        return ArchitectureModel(
            name=data["name"],
            file_path=file_path,
            status=data.get("status", "In Work"),
            is_deleted=data.get("is_deleted", False)
        )

class ArchitectureManager:
    """
    Manages the collection of Architecture Models.
    Handles creation, deletion, duplication, and persistence.
    """
    def __init__(self, project_path=None):
        self.project_path = project_path
        self.models: List[ArchitectureModel] = []
        self.active_model_index = 0
        
        if self.project_path:
            self.load_registry()
        else:
            self.create_default_model(in_memory=True)

    def set_project_path(self, new_path):
        """
        Updates the project path. Validates and moves in-memory models to files if needed.
        """
        self.project_path = new_path
        if not new_path:
            return

        # Update all models
        for model in self.models:
            if not model.file_path and model.name:
                # Assign new path
                filename = f"{model.name.replace(' ', '_')}.json"
                model.file_path = os.path.join(new_path, filename)
            elif model.file_path:
                # Re-root the path just in case
                fname = os.path.basename(model.file_path)
                model.file_path = os.path.join(new_path, fname)
                
            # If we have cached data, ensure it gets saved eventually (caller should trigger save)

    def load_registry(self):
        config_file = os.path.join(self.project_path, "architecture_models_registry.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    self.models = [ArchitectureModel.from_dict(m, self.project_path) for m in data.get("models", [])]
                    # Restore active index
                    self.active_model_index = data.get("active_index", 0)
            except Exception as e:
                print(f"Error loading architecture registry: {e}")
        
        if not self.models:
            self.create_default_model()
            
    def get_registry_file_path(self):
        if self.project_path:
            return os.path.join(self.project_path, "architecture_models_registry.json")
        return None

    def save_registry(self):
        if not self.project_path:
            return # Cannot save to disk yet

        data = {
            "models": [m.to_dict() for m in self.models],
            "active_index": self.active_model_index
        }
        try:
            with open(self.get_registry_file_path(), 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving architecture registry: {e}")

    def create_default_model(self, in_memory=False):
        if in_memory:
            model = ArchitectureModel("Architecture 1", None, "In Work", data_cache={"rows": []})
        else:
            path = os.path.join(self.project_path, "Architecture_1.json")
            model = ArchitectureModel("Architecture_1", path, "In Work")
            
        self.models.append(model)
        self.active_model_index = 0
        if not in_memory:
            self.save_registry()

    def create_model(self, name, status, copy_from_index=None):
        """Creates a new model."""
        filename = f"{name.replace(' ', '_')}.json"
        
        file_path = None
        if self.project_path:
            # Ensure unique filename
            counter = 1
            base_filename = filename
            while os.path.exists(os.path.join(self.project_path, filename)):
                 name_part, ext = os.path.splitext(base_filename)
                 filename = f"{name_part}_{counter}{ext}"
                 counter += 1
            file_path = os.path.join(self.project_path, filename)
        
        new_model = ArchitectureModel(name, file_path, status)
        
        # Handle Data Copying
        data_to_copy = {"rows": []}
        
        if copy_from_index is not None and 0 <= copy_from_index < len(self.models):
            src_model = self.models[copy_from_index]
            
            # If source has valid file, copy it physically
            if src_model.file_path and os.path.exists(src_model.file_path) and file_path:
                import shutil
                shutil.copy2(src_model.file_path, file_path)
            # If source is in memory or we are in memory, use cache/read
            elif src_model.file_path and os.path.exists(src_model.file_path):
                 # We are creating in memory, but source is on disk
                 with open(src_model.file_path, 'r') as f:
                     data_to_copy = json.load(f)
                 new_model.data_cache = data_to_copy
            elif src_model.data_cache:
                 new_model.data_cache = copy.deepcopy(src_model.data_cache)
                 
        else:
            # Empty
            if not file_path:
                new_model.data_cache = {"rows": []}
            else:
                 with open(file_path, 'w') as f:
                     json.dump({"rows": []}, f)

        self.models.append(new_model)
        self.save_registry()
        return new_model

    def soft_delete_model(self, index):
        if 0 <= index < len(self.models):
            self.models[index].is_deleted = True
            # If deleting the active model, switch to another if possible?
            # The controller should handle this ui-side usually.
            self.save_registry()
            return True
        return False

    def restore_model(self, index):
        if 0 <= index < len(self.models):
            self.models[index].is_deleted = False
            self.save_registry()
            return True
        return False

    def get_active_model(self):
        if 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return None

    def set_active_model(self, index):
        """Sets the active model index."""
        if 0 <= index < len(self.models):
            self.active_model_index = index
            self.save_registry()
            return self.models[index]
        return None

    def get_real_index_from_visible(self, visible_index):
        """Maps a visual row index (skipping deleted items) to the actual index in self.models"""
        visible_count = 0
        for i, m in enumerate(self.models):
            if not m.is_deleted:
                if visible_count == visible_index:
                    return i
                visible_count += 1
        return -1

    def set_active_model(self, index):
        real_index = self.get_real_index_from_visible(index) if index != -1 else -1 # Logic mismatch risk here
        # Actually caller passes real index usually?
        # Let's assume index is REAL index here
        if 0 <= index < len(self.models):
            self.active_model_index = index
            self.save_registry()
            return self.models[index]
        return None
        
    def move_model(self, old_index, new_index):
        if 0 <= old_index < len(self.models) and 0 <= new_index < len(self.models):
            item = self.models.pop(old_index)
            self.models.insert(new_index, item)
            
            # Update active index
            if self.active_model_index == old_index:
                self.active_model_index = new_index
            elif old_index < self.active_model_index <= new_index:
                self.active_model_index -= 1
            elif new_index <= self.active_model_index < old_index:
                self.active_model_index += 1
                
            self.save_registry()
            return True
        return False

    def preload_all_models(self):
        """
        Loads all models from disk into memory (data_cache).
        This ensures that column operations (which might rely on in-memory data for consistency)
        work correctly across all models without data loss.
        """
        for model in self.models:
            if model.file_path and os.path.exists(model.file_path):
                # Only load if not already in memory
                if model.data_cache is None:
                    try:
                        with open(model.file_path, 'r') as f:
                            model.data_cache = json.load(f)
                    except Exception as e:
                        print(f"Error pre-loading model '{model.name}': {e}")


class ArchitectureListModel(QAbstractListModel):
    """
    Qt Model to bridge ArchitectureManager data to QListView
    """
    
    ModelRole = Qt.ItemDataRole.UserRole + 1
    
    def __init__(self, manager: ArchitectureManager):
        super().__init__()
        self.manager = manager
    
    def rowCount(self, parent=QModelIndex()):
        # Only count visible items
        return len([m for m in self.manager.models if not m.is_deleted])

    def data(self, index, role):
        if not index.isValid():
            return None
        
        visible_models = [m for m in self.manager.models if not m.is_deleted]
        if index.row() >= len(visible_models):
            return None
            
        model = visible_models[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return model.name
            
        elif role == Qt.ItemDataRole.BackgroundRole:
            # Color indicator for status (Full Cell)
            if model.status == "Released":
                return QColor("green")
            elif model.status == "In Work":
                return QColor("#DAA520") # GoldenRod
            elif model.status == "Retired":
                return QColor("red")
                
        elif role == Qt.ItemDataRole.ForegroundRole:
            # High contrast text color
            if model.status == "Released":
                return QColor("white")
            elif model.status == "In Work":
                return QColor("black") 
            elif model.status == "Retired":
                return QColor("white")
        
        elif role == Qt.ItemDataRole.FontRole:
            # Bold the currently active model
            # We need to map visual row to real index
            real_index = self.get_real_index(index.row())
            if real_index == self.manager.active_model_index:
                 font = QtGui.QFont()
                 font.setBold(True)
                 return font
                
        elif role == self.ModelRole:
            return model
            
        return None

    def get_real_index(self, row):
        """Maps visual row index to actual list index in manager.models (skipping deleted ones)"""
        visible_count = 0
        for i, m in enumerate(self.manager.models):
            if not m.is_deleted:
                if visible_count == row:
                    return i
                visible_count += 1
        return -1

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
        
        # Calculate destination
        if row == -1:
            if parent.isValid():
                row = parent.row()
            else:
                row = self.rowCount()
        
        # Adjust for removal
        if row > src_row:
            row -= 1
            
        # Get real indices
        real_src = self.get_real_index(src_row)
        real_dst = self.get_real_index(row)
        
        # Perform move
        if self.manager.move_model(real_src, real_dst):
             self.refresh()
             return True
             
        return False

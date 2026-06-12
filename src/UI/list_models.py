"""
Qt list models bridging the (Qt-free) managers to QListView — moved out of
Application_Logic/Logic_Architecture_Models.py and Logic_Release_Manager.py
in Phase 0 of the pywebview migration. Retired with the rest of the PyQt UI
in Phase 4.
"""

from PyQt6.QtCore import (
    QAbstractListModel, Qt, QModelIndex, QMimeData, QByteArray,
    QDataStream, QIODevice, QSize,
)
from PyQt6.QtGui import QColor, QFont

from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Release_Manager import ReleaseManager


class ArchitectureListModel(QAbstractListModel):
    """Qt Model to bridge ArchitectureManager data to QListView."""

    ModelRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, manager: ArchitectureManager):
        super().__init__()
        self.manager = manager

    def rowCount(self, parent=QModelIndex()):
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
            if model.status == "Released":
                return QColor("green")
            elif model.status == "In Work":
                return QColor("#DAA520")
            elif model.status == "Retired":
                return QColor("red")
        elif role == Qt.ItemDataRole.ForegroundRole:
            if model.status in ("Released", "Retired"):
                return QColor("white")
            elif model.status == "In Work":
                return QColor("black")
        elif role == Qt.ItemDataRole.FontRole:
            real_index = self.get_real_index(index.row())
            if real_index == self.manager.active_model_index:
                font = QFont()
                font.setBold(True)
                return font
        elif role == Qt.ItemDataRole.SizeHintRole:
            # Taller rows give a comfortably larger click target for selecting
            # the active architecture model.
            return QSize(0, 34)
        elif role == self.ModelRole:
            return model
        return None

    def get_real_index(self, row: int) -> int:
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

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def flags(self, index):
        default_flags = super().flags(index)
        if index.isValid():
            return (default_flags | Qt.ItemFlag.ItemIsDragEnabled |
                    Qt.ItemFlag.ItemIsDropEnabled |
                    Qt.ItemFlag.ItemIsSelectable |
                    Qt.ItemFlag.ItemIsEnabled)
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
            row = parent.row() if parent.isValid() else self.rowCount()
        if row > src_row:
            row -= 1
        real_src = self.get_real_index(src_row)
        real_dst = self.get_real_index(row)
        if self.manager.move_model(real_src, real_dst):
            self.refresh()
            return True
        return False


class ReleaseListModel(QAbstractListModel):
    """Qt Model to bridge ReleaseManager data to QListView."""

    ModelRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, manager: ReleaseManager):
        super().__init__()
        self.manager = manager

    def rowCount(self, parent=QModelIndex()):
        return len(self.manager.releases)

    def data(self, index, role):
        if not index.isValid() or index.row() >= len(self.manager.releases):
            return None
        release = self.manager.releases[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            name = release.name
            if release.is_baseline:
                name += " [BASELINE]"
            return name
        elif role == Qt.ItemDataRole.BackgroundRole:
            if release.is_baseline:
                return QColor("#d3d3d3")
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

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def flags(self, index):
        default_flags = super().flags(index)
        if index.isValid():
            return (default_flags | Qt.ItemFlag.ItemIsDragEnabled |
                    Qt.ItemFlag.ItemIsDropEnabled |
                    Qt.ItemFlag.ItemIsSelectable |
                    Qt.ItemFlag.ItemIsEnabled)
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
            row = parent.row() if parent.isValid() else self.rowCount()
        if row > src_row:
            row -= 1
        if self.manager.move_release(src_row, row):
            self.refresh()
            return True
        return False

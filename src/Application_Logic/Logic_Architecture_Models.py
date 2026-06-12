from dataclasses import dataclass, field
import copy
from typing import List, Optional
from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice, QSize
from PyQt6.QtGui import QColor, QFont
from PyQt6 import QtGui


def _cell_text(cell) -> str:
    """Best-effort display text of a table cell (dict with widget_text/text, or a
    bare value). Shared by port-state propagation (#8.1/#8.2) and the picker dialog."""
    if isinstance(cell, dict):
        return (cell.get("widget_text") or cell.get("text") or "").strip()
    return str(cell).strip() if cell not in (None, "") else ""


@dataclass
class ArchitectureModel:
    name: str
    id: Optional[int] = None          # DB primary key (None before first save)
    status: str = "In Work"           # "Released" | "In Work" | "Retired"
    is_deleted: bool = False
    data_cache: Optional[dict] = None # In-memory buffer; backed by DB
    sort_order: int = 0
    metadata: dict = field(default_factory=dict)


class ArchitectureManager:
    """
    Manages Architecture Models, backed by a ProjectDatabase.
    project_path holds the .arch DB file path (None = unsaved).
    """

    def __init__(self, project_path=None):
        self.project_path = project_path   # .arch file path or None
        self._db = None                    # ProjectDatabase instance
        self.models: List[ArchitectureModel] = []
        self.active_model_index: int = 0

        if project_path:
            # Legacy init path — actual DB wiring happens via set_db()
            pass
        else:
            self._create_default_model_in_memory()

    # ------------------------------------------------------------------
    # DB wiring
    # ------------------------------------------------------------------

    def set_db(self, db):
        """Wire the manager to a ProjectDatabase and load state from it."""
        self._db = db
        self.project_path = db.db_path
        self.load_registry()

    def set_project_path(self, new_path):
        """Compatibility shim — callers pass the DB file path."""
        self.project_path = new_path

    # ------------------------------------------------------------------
    # Registry load / save
    # ------------------------------------------------------------------

    def load_registry(self):
        if not self._db:
            return
        rows = self._db.get_all_models()
        if not rows:
            # Empty DB — create a default model
            mid = self._db.create_model("Architecture_1", "In Work", 0)
            self._db.commit()
            self.models = [ArchitectureModel("Architecture_1", id=mid, status="In Work")]
            self.active_model_index = 0
            return

        self.models = [
            ArchitectureModel(
                name=r["name"],
                id=r["id"],
                status=r["status"],
                is_deleted=bool(r["is_deleted"]),
                sort_order=r["sort_order"]
            )
            for r in rows
        ]
        # Restore active index
        active_id_str = self._db.get_ui_state("active_model_id")
        self.active_model_index = 0
        if active_id_str:
            try:
                active_id = int(active_id_str)
                for i, m in enumerate(self.models):
                    if m.id == active_id:
                        self.active_model_index = i
                        break
            except ValueError:
                pass

    def save_registry(self):
        if not self._db:
            return
        for m in self.models:
            if m.id is None:
                m.id = self._db.create_model(m.name, m.status, m.sort_order)
            else:
                self._db.update_model(
                    m.id,
                    name=m.name,
                    status=m.status,
                    is_deleted=int(m.is_deleted),
                    sort_order=m.sort_order
                )
        active = self.get_active_model()
        if active and active.id:
            self._db.set_ui_state("active_model_id", str(active.id))
        self._db.commit()

    # ------------------------------------------------------------------
    # Model data persistence
    # ------------------------------------------------------------------

    def preload_all_models(self):
        """Lazy: only load the active model now; others are loaded on demand."""
        if not self._db:
            return
        active = self.get_active_model()
        if active and active.id is not None and active.data_cache is None:
            self._load_model_data(active)

    def _load_model_data(self, model: "ArchitectureModel"):
        """Load row data for a single model from DB into its cache."""
        if not self._db or model.id is None:
            return
        rows = self._db.get_model_rows(model.id)
        if model.data_cache is None:
            model.data_cache = {"rows": rows}
        else:
            model.data_cache["rows"] = rows
        # Merge persisted metadata (column_metadata, release_results,
        # linked_release_column) directly into data_cache so that all
        # consuming code (load_active_model_to_table, _restore_row_logic, etc.)
        # can find them via data_cache.get(key) — the old model.metadata
        # attribute was a separate dict that consuming code never read.
        meta = self._db.get_model_metadata(model.id)
        if meta:
            model.data_cache.update(meta)
        model.metadata = meta

    def save_model_data(self, model: ArchitectureModel):
        """Persist model.data_cache rows to DB."""
        if not self._db or model.id is None or model.data_cache is None:
            return
        rows = model.data_cache.get("rows", [])
        self._db.save_model_rows(model.id, rows)
        self._db.save_model_metadata(model.id, model.metadata)

    def propagate_status_to_ports(self, model, old_status, new_status,
                                  port_state_columns=("Port State",),
                                  selected_ports=None, port_name_column=None):
        """#8.1/#8.2: When a model leaves 'In Work' (e.g. In Work → Released/Retired),
        bump its rows' Port State from 'In Work' to the new model state.

        Strictly scoped: only the In Work → other transition, and only port cells
        whose value is still 'In Work' — Released / Retired / Deleted ports are left
        untouched. Persists the changed rows. Returns the number of cells changed.

        #8.2: the cascade is no longer silent — the caller (manager dialog) lets the
        user confirm/select which ports follow. When ``selected_ports`` is given (an
        iterable of port names), only rows whose ``port_name_column`` value is in that
        set are updated; ``selected_ports=None`` keeps the original 'all In Work ports'
        behaviour for back-compat.
        """
        if old_status != "In Work" or new_status == "In Work":
            return 0
        if model is None:
            return 0
        if model.data_cache is None:
            self._load_model_data(model)
        if not model.data_cache:
            return 0
        selected = set(selected_ports) if selected_ports is not None else None
        rows = model.data_cache.get("rows", [])
        changed = 0
        for row in rows:
            if selected is not None:
                pname = _cell_text(row.get(port_name_column)) if port_name_column else ""
                if pname not in selected:
                    continue
            for col_name in port_state_columns:
                cell = row.get(col_name)
                if not isinstance(cell, dict):
                    continue
                current = (cell.get("widget_text") or cell.get("text") or "").strip()
                if current == "In Work":
                    cell["text"] = new_status
                    cell["widget_text"] = new_status
                    changed += 1
        if changed:
            self.save_model_data(model)
            if self._db:
                self._db.commit()
        return changed

    def save_all_model_data(self):
        """
        Persist every in-memory model's rows + metadata to the DB.

        The active model is normally flushed from the live table separately, but
        models created during a multi-sheet import only ever live in data_cache
        until this runs — without it, every model except the active one is lost
        on save.  Rows/metadata are taken from each model's data_cache; metadata
        keys mirror flush_current_data_to_model().
        """
        if not self._db:
            return
        for m in self.models:
            if m.id is None or m.data_cache is None:
                continue
            rows = m.data_cache.get("rows", [])
            self._db.save_model_rows(m.id, rows)
            meta_to_save = {}
            for key in ("column_metadata", "release_results", "linked_release_column"):
                val = m.data_cache.get(key)
                if val:
                    meta_to_save[key] = val
            self._db.save_model_metadata(m.id, meta_to_save)
        self._db.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _create_default_model_in_memory(self):
        self.models = [ArchitectureModel("Architecture 1", id=None, status="In Work",
                                          data_cache={"rows": []})]
        self.active_model_index = 0

    def create_model(self, name: str, status: str, copy_from_index=None) -> ArchitectureModel:
        new_model = ArchitectureModel(name=name, status=status,
                                      sort_order=len(self.models))
        if copy_from_index is not None and 0 <= copy_from_index < len(self.models):
            src = self.models[copy_from_index]
            new_model.metadata = copy.deepcopy(src.metadata)
            if src.data_cache:
                new_model.data_cache = copy.deepcopy(src.data_cache)
            elif self._db and src.id is not None:
                new_model.data_cache = {"rows": self._db.get_model_rows(src.id)}
        else:
            new_model.data_cache = {"rows": []}

        if self._db:
            new_model.id = self._db.create_model(name, status, new_model.sort_order)
            if copy_from_index is not None:
                if new_model.data_cache:
                    self._db.save_model_rows(new_model.id,
                                              new_model.data_cache.get("rows", []))
                self._db.save_model_metadata(new_model.id, new_model.metadata)
            self._db.commit()

        self.models.append(new_model)
        self.save_registry()
        return new_model

    def soft_delete_model(self, index: int) -> bool:
        if 0 <= index < len(self.models):
            self.models[index].is_deleted = True
            self.save_registry()
            return True
        return False

    def restore_model(self, index: int) -> bool:
        if 0 <= index < len(self.models):
            self.models[index].is_deleted = False
            self.save_registry()
            return True
        return False

    def get_active_model(self) -> Optional[ArchitectureModel]:
        if 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return None

    @property
    def active_model_id(self) -> Optional[int]:
        active = self.get_active_model()
        return active.id if active else None

    def get_real_index_from_visible(self, visible_index: int) -> int:
        visible_count = 0
        for i, m in enumerate(self.models):
            if not m.is_deleted:
                if visible_count == visible_index:
                    return i
                visible_count += 1
        return -1

    def set_active_model(self, index: int) -> Optional[ArchitectureModel]:
        if 0 <= index < len(self.models):
            self.active_model_index = index
            # Switching the active model only needs to persist *which* model is
            # active — not rewrite every model's registry row. The old
            # save_registry() here made each model switch do N row-writes + a commit
            # on the UI thread (a real cause of switch lag). The full registry is
            # still saved on create/delete/rename and on project save.
            m = self.models[index]
            if self._db and m.id is not None:
                self._db.set_ui_state("active_model_id", str(m.id))
                self._db.commit()
            return m
        return None

    def move_model(self, old_index: int, new_index: int) -> bool:
        if not (0 <= old_index < len(self.models) and
                0 <= new_index < len(self.models)):
            return False
        item = self.models.pop(old_index)
        self.models.insert(new_index, item)

        if self.active_model_index == old_index:
            self.active_model_index = new_index
        elif old_index < self.active_model_index <= new_index:
            self.active_model_index -= 1
        elif new_index <= self.active_model_index < old_index:
            self.active_model_index += 1

        # Update sort_order
        for i, m in enumerate(self.models):
            m.sort_order = i
        self.save_registry()
        return True

    def get_registry_file_path(self):
        """Legacy compatibility — returns None (no JSON file)."""
        return None


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
                font = QtGui.QFont()
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

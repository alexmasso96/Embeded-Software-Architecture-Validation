from dataclasses import dataclass
import datetime
import copy
from typing import List, Optional
from .Logic_File_Locking import FileLockManager


@dataclass
class ReleaseModel:
    name: str
    id: Optional[int] = None          # DB primary key
    is_baseline: bool = False
    parent_release_name: Optional[str] = None
    data_cache: Optional[dict] = None # In-memory buffer (rows + column_metadata + release_results)
    description: str = ""
    timestamp: str = ""
    elf_path: Optional[str] = None
    elf_hash: Optional[str] = None
    is_deleted: bool = False
    deletion_comment: str = ""
    sort_order: int = 0


class ReleaseManager:
    """
    Manages Software Releases and Baselines, backed by a ProjectDatabase.
    project_path holds the .arch file path (None = unsaved).
    """

    def __init__(self, project_path=None):
        self.project_path = project_path
        self._db = None
        self.releases: List[ReleaseModel] = []
        self.active_release_index: int = -1

    # ------------------------------------------------------------------
    # DB wiring
    # ------------------------------------------------------------------

    def set_db(self, db):
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
        rows = self._db.get_all_releases()
        self.releases = []
        self.active_release_index = -1
        for r in rows:
            rel = ReleaseModel(
                name=r["name"],
                id=r["id"],
                is_baseline=bool(r["is_baseline"]),
                parent_release_name=r["parent_release_name"],
                description=r["description"] or "",
                timestamp=r["timestamp"] or "",
                elf_path=r["elf_path"],
                elf_hash=r["elf_hash"],
                is_deleted=bool(r["is_deleted"]),
                deletion_comment=r["deletion_comment"] or "",
                sort_order=r["sort_order"]
            )
            self.releases.append(rel)
            if r["is_active"]:
                self.active_release_index = len(self.releases) - 1

    def save_registry(self):
        if not self._db:
            return
        for r in self.releases:
            if r.id is None:
                r.id = self._db.create_release(
                    name=r.name,
                    is_baseline=int(r.is_baseline),
                    parent_release_name=r.parent_release_name,
                    description=r.description,
                    timestamp=r.timestamp,
                    elf_path=r.elf_path,
                    elf_hash=r.elf_hash,
                    sort_order=r.sort_order
                )
            else:
                self._db.update_release(
                    r.id,
                    name=r.name,
                    is_baseline=int(r.is_baseline),
                    parent_release_name=r.parent_release_name,
                    description=r.description,
                    timestamp=r.timestamp,
                    elf_path=r.elf_path,
                    elf_hash=r.elf_hash,
                    is_deleted=int(r.is_deleted),
                    deletion_comment=r.deletion_comment,
                    sort_order=r.sort_order,
                    is_active=0
                )
        active = self.get_active_release()
        if active and active.id:
            self._db.set_active_release(active.id)
        else:
            self._db.set_active_release(None)
        self._db.commit()

    # ------------------------------------------------------------------
    # Release data persistence
    # ------------------------------------------------------------------

    def _load_data(self, release: ReleaseModel) -> dict:
        if release.data_cache is not None:
            return release.data_cache
        if self._db and release.id is not None:
            rows = self._db.get_release_rows(release.id)
            col_meta = self._db.get_release_column_metadata(release.id)
            results = self._db.get_release_results(release.id)
            linked = self._db.get_release_linked_column(release.id)
            data = {"rows": rows, "column_metadata": col_meta, "release_results": results}
            if linked:
                data["linked_release_column"] = linked
            release.data_cache = data
            return data
        return {"rows": []}

    def _save_data(self, release: ReleaseModel, data: dict):
        release.data_cache = data
        if self._db and release.id is not None:
            self._db.save_release_rows(release.id, data.get("rows", []))
            col_meta = data.get("column_metadata", {})
            if col_meta:
                self._db.save_release_column_metadata(release.id, col_meta)
            results = data.get("release_results", {})
            if results:
                self._db.save_release_results(release.id, results)
            linked = data.get("linked_release_column")
            self._db.save_release_linked_column(release.id, linked)
            self._db.commit()

    def flush_active_release_data(self):
        if self._db and getattr(self._db, "read_only", False):
            return
        active = self.get_active_release()
        if active and active.data_cache:
            self._save_data(active, active.data_cache)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_release(self, name: str, description: str = "",
                       copy_from_active: bool = False,
                       elf_path=None, elf_hash=None, elf_data=None,
                       baseline_previous: bool = False) -> ReleaseModel:
        if any(r.name == name for r in self.releases):
            raise ValueError(f"Release '{name}' already exists.")

        ts = datetime.datetime.now().isoformat()
        new_release = ReleaseModel(
            name=name,
            is_baseline=False,
            description=description,
            timestamp=ts,
            elf_path=elf_path,
            elf_hash=elf_hash,
            sort_order=0
        )

        active = self.get_active_release()

        # baseline the previous release if requested
        if baseline_previous and active:
            active.is_baseline = True
            if self._db and active.id is not None:
                self._db.update_release(active.id, is_baseline=1)
                # NC-4: the explicit Freeze/Unfreeze *button* logs the event; the
                # auto-baseline-on-create flow keeps a clean history snapshot
                # (the new release's creation is itself the record), so we do NOT
                # log here — it would be cloned into the new release by the
                # subsequent copy_release_history and pollute the snapshot.

        data: dict = {"rows": []}
        if copy_from_active and active:
            data = copy.deepcopy(self._load_data(active))
            data.pop("database", None)  # strip legacy ELF blob if present

        if elf_data:
            # Legacy: caller may pass an elf_data blob — we ignore it (ELF lives in DB now)
            pass

        new_release.data_cache = data

        if self._db:
            new_release.id = self._db.create_release(
                name=name, is_baseline=0,
                description=description, timestamp=ts,
                elf_path=elf_path, elf_hash=elf_hash,
                sort_order=0
            )
            self._db.save_release_rows(new_release.id, data.get("rows", []))
            # Snapshot history to new release
            if copy_from_active and active and active.id is not None:
                self._db.copy_release_history(active.id, new_release.id)
            self._db.commit()

        # Shift existing sort orders
        for r in self.releases:
            r.sort_order += 1
        new_release.sort_order = 0

        self.releases.insert(0, new_release)
        self.active_release_index = 0
        self.save_registry()
        return new_release

    def branch_release(self, src_index: int, name: str,
                       description: str = "") -> ReleaseModel:
        """Fork a new software release off an existing one (Release & Baseline
        Manager). Clones the source release's rows + validation state (column
        metadata, release results, linked-column) as the new branch's starting
        point and chains it to the source via ``parent_release_name``. The new
        branch is inserted at the front and made active (mirrors create_release).
        """
        if not (0 <= src_index < len(self.releases)):
            raise ValueError("Invalid source release index.")
        name = name.strip()
        if not name:
            raise ValueError("Branch name cannot be empty.")
        if any(r.name == name for r in self.releases):
            raise ValueError(f"Release '{name}' already exists.")

        src = self.releases[src_index]
        ts = datetime.datetime.now().isoformat()

        # Snapshot the source's data (rows + validation state). deepcopy so later
        # edits on the branch never bleed back into the parent's cache.
        data = copy.deepcopy(self._load_data(src))
        data.pop("database", None)  # strip legacy ELF blob if present

        new_release = ReleaseModel(
            name=name,
            is_baseline=False,
            parent_release_name=src.name,
            description=description,
            timestamp=ts,
            elf_path=src.elf_path,
            elf_hash=src.elf_hash,
            sort_order=0,
        )
        new_release.data_cache = data

        if self._db:
            new_release.id = self._db.create_release(
                name=name, is_baseline=0,
                parent_release_name=src.name,
                description=description, timestamp=ts,
                elf_path=src.elf_path, elf_hash=src.elf_hash,
                sort_order=0,
            )
            self._db.save_release_rows(new_release.id, data.get("rows", []))
            col_meta = data.get("column_metadata", {})
            if col_meta:
                self._db.save_release_column_metadata(new_release.id, col_meta)
            results = data.get("release_results", {})
            if results:
                self._db.save_release_results(new_release.id, results)
            linked = data.get("linked_release_column")
            if linked:
                self._db.save_release_linked_column(new_release.id, linked)
            if src.id is not None:
                self._db.copy_release_history(src.id, new_release.id)
            self._db.commit()

        # Shift existing sort orders so the new branch sits at the front.
        for r in self.releases:
            r.sort_order += 1
        new_release.sort_order = 0

        self.releases.insert(0, new_release)
        self.active_release_index = 0
        self.save_registry()
        return new_release

    def log_baseline_event(self, release, frozen: bool):
        """NC-4: record a baseline freeze/unfreeze in the change history so it is
        plainly visible — logged against BOTH the affected release and the
        active/main release (so it shows up on the main project timeline too)."""
        if not self._db:
            return
        actor = FileLockManager.get_username()
        action = "Froze" if frozen else "Unfroze"
        desc = f"{action} baseline '{getattr(release, 'name', '')}'"
        targets = set()
        if getattr(release, "id", None) is not None:
            targets.add(release.id)
        active = self.get_active_release()
        if active and active.id is not None:
            targets.add(active.id)
        for rid in targets:
            try:
                self._db.add_history_entry(description=desc, model_name="",
                                           username=actor, release_id=rid)
            except Exception:
                pass

    def create_baseline(self, release_index: int, baseline_name: str,
                        layout_data=None, active_model_data=None) -> ReleaseModel:
        if not self._db:
            raise ValueError("No active project database.")
        baseline_name = baseline_name.strip()
        if not baseline_name:
            raise ValueError("Baseline name cannot be empty.")
        if any(r.name == baseline_name and not r.is_deleted for r in self.releases):
            raise ValueError(f"A release or baseline named '{baseline_name}' already exists.")
        if not (0 <= release_index < len(self.releases)):
            raise ValueError("Invalid release index.")
        src = self.releases[release_index]
        if src.is_baseline:
            raise ValueError("Cannot create a baseline from a baseline.")

        ts = datetime.datetime.now().isoformat()
        snapshot_data = {}
        if active_model_data:
            snapshot_data["rows"] = active_model_data.get("rows", [])
            snapshot_data["column_metadata"] = active_model_data.get("column_metadata", {})
            snapshot_data["release_results"] = active_model_data.get("release_results", {})

        new_id = self._db.create_release(
            name=baseline_name,
            is_baseline=1,
            parent_release_name=src.name,
            description=f"Snapshot of {src.name}",
            timestamp=ts,
            elf_path=src.elf_path,
            elf_hash=src.elf_hash,
            sort_order=len(self.releases)
        )
        # NC-5: the baseline is created frozen (is_baseline=1); populate its
        # snapshot once via the explicit bypass, then it is DB-write-protected.
        self._db.save_release_rows(new_id, snapshot_data.get("rows", []), _allow_frozen=True)
        col_meta = snapshot_data.get("column_metadata", {})
        if col_meta:
            self._db.save_release_column_metadata(new_id, col_meta, _allow_frozen=True)
        results = snapshot_data.get("release_results", {})
        if results:
            self._db.save_release_results(new_id, results, _allow_frozen=True)

        # Snapshot history to the baseline
        if src.id is not None:
            self._db.copy_release_history(src.id, new_id)

        if layout_data:
            self._db.set_meta(f"baseline_layout_{new_id}", __import__("json").dumps(layout_data))

        self._db.commit()

        new_baseline = ReleaseModel(
            name=baseline_name,
            id=new_id,
            is_baseline=True,
            parent_release_name=src.name,
            description=f"Snapshot of {src.name}",
            timestamp=ts,
            elf_path=src.elf_path,
            elf_hash=src.elf_hash,
            data_cache=snapshot_data,
            sort_order=len(self.releases)
        )
        self.releases.append(new_baseline)
        self.save_registry()
        return new_baseline

    def rename_release(self, index: int, new_name: str):
        if not (0 <= index < len(self.releases)):
            return False, "Invalid index"
        model = self.releases[index]
        if model.is_baseline:
            return False, "Cannot rename baselines"
        if any(r.name == new_name for r in self.releases if r is not model):
            return False, "Name already exists"
        model.name = new_name
        self.save_registry()
        return True, "Success"

    def delete_release(self, index: int, deletion_comment: str = ""):
        if not (0 <= index < len(self.releases)):
            return False, "Invalid index"
        model = self.releases[index]
        if not model.is_baseline:
            has_baseline = any(
                r.is_baseline and not r.is_deleted and r.parent_release_name == model.name
                for r in self.releases
            )
            if has_baseline:
                return False, "Cannot delete release that has active baselines."
        if model.is_baseline:
            model.is_deleted = True
            model.deletion_comment = deletion_comment
            self.save_registry()
            return True, "Soft-deleted"

        # Permanent delete
        if self._db and model.id is not None:
            self._db.delete_release_record(model.id)
            self._db.commit()
        self.releases.pop(index)
        if self.active_release_index == index:
            self.active_release_index = -1
        elif self.active_release_index > index:
            self.active_release_index -= 1
        self.save_registry()
        return True, "Deleted"

    def restore_release(self, index: int):
        """Un-delete a soft-deleted baseline (Release Manager "Restore"). Only
        baselines soft-delete, so this is the inverse of that path; refuses if a
        live release/baseline already claims the name."""
        if not (0 <= index < len(self.releases)):
            return False, "Invalid index"
        model = self.releases[index]
        if not model.is_deleted:
            return True, "Not deleted"
        if any(r.name == model.name and not r.is_deleted and r is not model
               for r in self.releases):
            return False, "Name already exists"
        model.is_deleted = False
        model.deletion_comment = ""
        self.save_registry()
        return True, "Restored"

    def selectable_releases(self) -> List[ReleaseModel]:
        """#2E: the releases offered in every source/release picker — real software
        releases only (exclude frozen baseline snapshots and soft-deleted ones).
        Order matches the registry (newest first, since create_release inserts at 0)."""
        return [r for r in self.releases if not r.is_baseline and not r.is_deleted]

    def get_active_release(self) -> Optional[ReleaseModel]:
        if 0 <= self.active_release_index < len(self.releases):
            return self.releases[self.active_release_index]
        return None

    def set_active_release(self, index: int) -> Optional[ReleaseModel]:
        if not (0 <= index < len(self.releases)):
            return None
        # Unload previous
        if self.active_release_index != -1 and self.active_release_index != index:
            self.releases[self.active_release_index].data_cache = None
        self.active_release_index = index
        self.save_registry()
        new_release = self.releases[index]
        if new_release.data_cache is None:
            self._load_data(new_release)
        return new_release

    def move_release(self, old_index: int, new_index: int) -> bool:
        if not (0 <= old_index < len(self.releases) and
                0 <= new_index < len(self.releases)):
            return False
        item = self.releases.pop(old_index)
        self.releases.insert(new_index, item)
        if self.active_release_index == old_index:
            self.active_release_index = new_index
        elif old_index < self.active_release_index <= new_index:
            self.active_release_index -= 1
        elif new_index <= self.active_release_index < old_index:
            self.active_release_index += 1
        for i, r in enumerate(self.releases):
            r.sort_order = i
        self.save_registry()
        return True

    def preload_all_releases(self):
        """No-op — releases are lazy-loaded."""
        pass

    def _ensure_directories(self):
        """No-op — no file system directories in DB mode."""
        pass



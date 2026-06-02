import datetime
import logging
from .Logic_File_Locking import FileLockManager

logger = logging.getLogger(__name__)


class HistoryManager:
    def __init__(self, db=None):
        self._db = db
        self.history = []
        if db and db.is_open:
            self.load_history()

    def set_db(self, db):
        self._db = db
        if db and db.is_open:
            self.load_history()

    def load_history(self):
        self.history = []
        if not self._db or not self._db.is_open:
            return
        try:
            self.history = self._db.get_history()
        except Exception as e:
            logger.exception("Failed to load history")

    def save_history(self):
        pass  # No-op: entries written immediately via add_entry()

    def add_entry(self, description: str, model_name: str = ""):
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user": FileLockManager.get_username(),
            "model": model_name,
            "description": description
        }
        self.history.append(entry)
        if self._db and self._db.is_open:
            try:
                self._db.add_history_entry(
                    description=description,
                    model_name=model_name,
                    username=entry["user"]
                )
            except Exception as e:
                logger.exception("Failed to persist history entry")

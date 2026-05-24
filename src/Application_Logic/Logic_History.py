import os
import json
import base64
import datetime
from .Logic_File_Locking import FileLockManager

class HistoryManager:
    def __init__(self, project_path=None):
        self.project_path = project_path
        self.history = []
        if project_path:
            self.load_history()

    def get_history_file_path(self) -> str:
        return os.path.join(self.project_path, "history.json")

    def load_history(self):
        self.history = []
        if not self.project_path:
            return
        
        path = self.get_history_file_path()
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    obfuscated_data = f.read()
                decoded_data = base64.b64decode(obfuscated_data).decode('utf-8')
                self.history = json.loads(decoded_data)
            except Exception as e:
                print(f"Failed to load history: {e}")
                self.history = []

    def save_history(self):
        if not self.project_path:
            return
        
        path = self.get_history_file_path()
        try:
            # We want to create directories if they don't exist, but .arch directory must exist since project is saved
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            data_str = json.dumps(self.history, indent=4)
            obfuscated_data = base64.b64encode(data_str.encode('utf-8'))
            with open(path, 'wb') as f:
                f.write(obfuscated_data)
        except Exception as e:
            print(f"Failed to save history: {e}")

    def add_entry(self, description: str, model_name: str = ""):
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user": FileLockManager.get_username(),
            "model": model_name,
            "description": description
        }
        self.history.append(entry)
        self.save_history()

import os
import json
import socket
import sys
import datetime
import getpass
import logging

logger = logging.getLogger(__name__)

LOCK_HEARTBEAT_INTERVAL_SECONDS = 60
LOCK_STALE_THRESHOLD_SECONDS = 600

class FileLockManager:
    @staticmethod
    def get_username():
        """Returns the current OS username cross-platform."""
        try:
            return os.getlogin()
        except Exception:
            try:
                return getpass.getuser()
            except Exception:
                return "unknown"

    @staticmethod
    def is_lock_stale(lock_data: dict) -> bool:
        """Checks if a lock's last_seen timestamp exceeds the stale threshold."""
        last_seen_str = lock_data.get("last_seen")
        if not last_seen_str:
            return True
        try:
            if last_seen_str.endswith('Z'):
                last_seen_str = last_seen_str[:-1] + '+00:00'
            last_seen = datetime.datetime.fromisoformat(last_seen_str)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            age = (now - last_seen).total_seconds()
            return age > LOCK_STALE_THRESHOLD_SECONDS
        except Exception:
            return True

    @staticmethod
    def is_process_alive(pid: int, hostname: str, lock_data: dict = None) -> bool:
        """Checks if the given PID is active on the host machine."""
        current_hostname = socket.gethostname()
        if hostname != current_hostname:
            # Different machine: we cannot check process status across machines, so assume it is alive
            if lock_data is not None:
                return not FileLockManager.is_lock_stale(lock_data)
            else:
                return True
            
        if pid <= 0:
            return False
            
        # Check if process is alive locally
        if sys.platform != "win32":
            try:
                os.kill(pid, 0)
                return True
            except OSError as err:
                import errno
                if err.errno == errno.ESRCH:
                    return False
                # EPERM means we don't have permission to signal but it exists
                return True
        else:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    exit_code = ctypes.c_ulong()
                    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    kernel32.CloseHandle(handle)
                    return exit_code.value == 259
                else:
                    last_error = kernel32.GetLastError()
                    return last_error == 5 # Access Denied
            except Exception:
                try:
                    import subprocess
                    # Run tasklist command to check if PID exists
                    out = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True, text=True)
                    return str(pid) in out
                except Exception:
                    return True

    @staticmethod
    def get_lock_file_path(project_path: str) -> str:
        """Returns the absolute path to the sidecar lock file for the project."""
        return project_path + ".lock"

    @staticmethod
    def check_lock(project_path: str) -> dict:
        """
        Checks lock status. Returns a dictionary:
        {
            "status": "unlocked" | "locked_by_me" | "locked_by_other",
            "user": str,
            "hostname": str,
            "timestamp": str,
            "pid": int
        }
        """
        lock_file = FileLockManager.get_lock_file_path(project_path)
        if not os.path.exists(lock_file):
            return {"status": "unlocked"}
            
        try:
            with open(lock_file, 'r') as f:
                data = json.load(f)
        except Exception:
            # Invalid lock file or read error. Treat as dead / unlocked
            return {"status": "unlocked"}
            
        user = data.get("user", "unknown")
        hostname = data.get("hostname", "unknown")
        timestamp = data.get("timestamp", "")
        pid = data.get("pid", 0)
        
        # Check if it is locked by the CURRENT process
        current_pid = os.getpid()
        current_hostname = socket.gethostname()
        
        if pid == current_pid and hostname == current_hostname:
            return {
                "status": "locked_by_me",
                "user": user,
                "hostname": hostname,
                "timestamp": timestamp,
                "pid": pid
            }
            
        # Check if the process is alive
        if FileLockManager.is_process_alive(pid, hostname, lock_data=data):
            return {
                "status": "locked_by_other",
                "user": user,
                "hostname": hostname,
                "timestamp": timestamp,
                "pid": pid
            }
        else:
            # Stale lock: process is dead. Treat as unlocked.
            return {"status": "unlocked"}

    @staticmethod
    def acquire_lock(project_path: str) -> tuple[bool, str]:
        """
        Attempts to acquire the lock.
        Returns (success, message).
        If lock is held by someone else, returns (False, error_msg).
        If acquired or already held by us, returns (True, success_msg).
        """
        if not project_path or not os.path.exists(project_path):
            return False, "Invalid project path."
            
        lock_status = FileLockManager.check_lock(project_path)
        if lock_status["status"] == "locked_by_other":
            user = lock_status["user"]
            hostname = lock_status["hostname"]
            timestamp = lock_status["timestamp"]
            return False, f"Project is locked by {user} on {hostname} since {timestamp}"
            
        lock_file = FileLockManager.get_lock_file_path(project_path)
        _now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lock_data = {
            "user": FileLockManager.get_username(),
            "hostname": socket.gethostname(),
            "timestamp": _now,
            "last_seen": _now,
            "pid": os.getpid()
        }

        if lock_status["status"] == "locked_by_me":
            # We already own the lock — safe to overwrite via temp+replace.
            try:
                temp_lock = f"{lock_file}.{os.getpid()}.tmp"
                with open(temp_lock, 'w') as f:
                    json.dump(lock_data, f, indent=4)
                os.replace(temp_lock, lock_file)
                return True, "Lock acquired successfully."
            except Exception as e:
                try:
                    if os.path.exists(temp_lock):
                        os.remove(temp_lock)
                except Exception:
                    pass
                return False, f"Failed to write lock file: {str(e)}"

        # Lock is unlocked — use O_CREAT|O_EXCL for an atomic create.
        # This prevents the TOCTOU race where two processes both see "unlocked"
        # and both succeed with temp+replace.
        for _attempt in range(2):
            try:
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                if sys.platform == "win32":
                    flags |= os.O_BINARY
                fd = os.open(lock_file, flags, 0o644)
                with os.fdopen(fd, 'w') as f:
                    json.dump(lock_data, f, indent=4)
                return True, "Lock acquired successfully."
            except FileExistsError:
                # Another process beat us — re-read and check staleness.
                recheck = FileLockManager.check_lock(project_path)
                if recheck["status"] == "unlocked":
                    # Stale lock was just cleaned up by check_lock; retry once.
                    try:
                        os.unlink(lock_file)
                    except OSError:
                        pass
                    continue
                # Genuinely held by someone else.
                user = recheck.get("user", "unknown")
                hostname = recheck.get("hostname", "unknown")
                timestamp = recheck.get("timestamp", "")
                return False, f"Project is locked by {user} on {hostname} since {timestamp}"
            except Exception as e:
                return False, f"Failed to write lock file: {str(e)}"
        return False, "Failed to acquire lock after retry."

    @staticmethod
    def release_lock(project_path: str) -> bool:
        """
        Releases the lock file if it is held by us (or if it is stale).
        Returns True if released, False otherwise.
        """
        if not project_path or not os.path.exists(project_path):
            return False
            
        lock_file = FileLockManager.get_lock_file_path(project_path)
        if not os.path.exists(lock_file):
            return True
            
        lock_status = FileLockManager.check_lock(project_path)
        # Release if locked by me or if it is stale (unlocked status)
        if lock_status["status"] in ("locked_by_me", "unlocked"):
            try:
                os.remove(lock_file)
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def write_heartbeat(project_path: str):
        """Updates the last_seen timestamp in the lock file to current time if held by us."""
        if not project_path:
            return
        lock_file = FileLockManager.get_lock_file_path(project_path)
        if not os.path.exists(lock_file):
            return
        try:
            with open(lock_file, 'r') as f:
                data = json.load(f)
            if data.get("pid") == os.getpid() and data.get("hostname") == socket.gethostname():
                data["last_seen"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with open(lock_file, 'w') as f:
                    json.dump(data, f, indent=4)
        except Exception as e:
            logger.exception("Failed to write lock heartbeat")


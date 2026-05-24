import sys
import os
import shutil
import json

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_File_Locking import FileLockManager

def test_file_locking():
    print("Running File Locking Unit Test...")
    
    test_dir = "test_locking_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    try:
        # Test 1: Initially unlocked
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "unlocked"
        print("Test 1: Lock is initially unlocked.")
        
        # Test 2: Acquire lock
        success, msg = FileLockManager.acquire_lock(test_dir)
        assert success is True
        print("Test 2: Lock acquired successfully.")
        
        # Test 3: Lock status check locked by me
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "locked_by_me"
        assert status["user"] == FileLockManager.get_username()
        print("Test 3: Lock status correctly reported as 'locked_by_me'.")
        
        # Test 4: Deny second acquisition by another context (simulated by editing PID in lock file)
        lock_file = FileLockManager.get_lock_file_path(test_dir)
        with open(lock_file, 'r') as f:
            data = json.load(f)
            
        # Change PID to parent process PID (which is guaranteed to be alive)
        parent_pid = os.getppid()
        data["pid"] = parent_pid
        with open(lock_file, 'w') as f:
            json.dump(data, f, indent=4)
            
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "locked_by_other"
        print("Test 4: Stably detects locked_by_other when PID is running elsewhere.")
        
        # Test 5: Re-acquire when lock is stale (PID is dead)
        data["pid"] = 999999 # Non-existent process PID
        with open(lock_file, 'w') as f:
            json.dump(data, f, indent=4)
            
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "unlocked" # Stale lock reported as unlocked
        
        # Attempt to acquire stale lock
        success, msg = FileLockManager.acquire_lock(test_dir)
        assert success is True
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "locked_by_me"
        print("Test 5: Successfully overrides stale locks and re-acquires.")
        
        # Test 6: Release lock
        success = FileLockManager.release_lock(test_dir)
        assert success is True
        status = FileLockManager.check_lock(test_dir)
        assert status["status"] == "unlocked"
        print("Test 6: Lock released successfully.")
        
        print("\nALL FILE LOCKING UNIT TESTS PASSED!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_file_locking()

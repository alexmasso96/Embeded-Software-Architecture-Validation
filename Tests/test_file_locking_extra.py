"""
Branch coverage for FileLockManager beyond the happy-path test_file_locking.py:
staleness detection, cross-machine process checks, heartbeat, and error paths.
"""
import os
import sys
import json
import socket
import datetime
import tempfile

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_File_Locking import (
    FileLockManager,
    LOCK_STALE_THRESHOLD_SECONDS,
)


def _iso(dt):
    return dt.isoformat()


# --------------------------------------------------------------------------
# get_username
# --------------------------------------------------------------------------

def test_get_username_returns_nonempty():
    assert FileLockManager.get_username()


# --------------------------------------------------------------------------
# is_lock_stale
# --------------------------------------------------------------------------

def test_is_lock_stale_missing_last_seen():
    assert FileLockManager.is_lock_stale({}) is True


def test_is_lock_stale_fresh():
    now = datetime.datetime.now(datetime.timezone.utc)
    assert FileLockManager.is_lock_stale({"last_seen": _iso(now)}) is False


def test_is_lock_stale_old():
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        seconds=LOCK_STALE_THRESHOLD_SECONDS + 60
    )
    assert FileLockManager.is_lock_stale({"last_seen": _iso(old)}) is True


def test_is_lock_stale_z_suffix_and_naive():
    # 'Z' suffix is normalized; naive datetime is treated as UTC
    fresh_naive = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    assert FileLockManager.is_lock_stale({"last_seen": fresh_naive}) is False
    assert FileLockManager.is_lock_stale({"last_seen": "2000-01-01T00:00:00Z"}) is True


def test_is_lock_stale_invalid_timestamp():
    assert FileLockManager.is_lock_stale({"last_seen": "not-a-date"}) is True


# --------------------------------------------------------------------------
# is_process_alive
# --------------------------------------------------------------------------

def test_is_process_alive_other_machine_uses_staleness():
    fresh = {"last_seen": _iso(datetime.datetime.now(datetime.timezone.utc))}
    stale = {"last_seen": "2000-01-01T00:00:00+00:00"}
    assert FileLockManager.is_process_alive(123, "some-other-host", fresh) is True
    assert FileLockManager.is_process_alive(123, "some-other-host", stale) is False
    # No lock_data -> assume alive on a different machine
    assert FileLockManager.is_process_alive(123, "some-other-host") is True


def test_is_process_alive_local_dead_and_alive():
    host = socket.gethostname()
    assert FileLockManager.is_process_alive(0, host) is False
    assert FileLockManager.is_process_alive(999999, host) is False
    assert FileLockManager.is_process_alive(os.getpid(), host) is True


# --------------------------------------------------------------------------
# check_lock error paths
# --------------------------------------------------------------------------

def test_check_lock_corrupt_file_treated_as_unlocked():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        with open(FileLockManager.get_lock_file_path(proj), "w") as f:
            f.write("{ not valid json")
        assert FileLockManager.check_lock(proj)["status"] == "unlocked"


# --------------------------------------------------------------------------
# acquire_lock / release_lock edge cases
# --------------------------------------------------------------------------

def test_acquire_lock_invalid_path():
    ok, msg = FileLockManager.acquire_lock("/no/such/project.arch")
    assert ok is False
    assert "Invalid" in msg


def test_acquire_lock_locked_by_other():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        # Write a lock owned by a live process (parent) so it reads as locked_by_other
        lock_data = {
            "user": "someone",
            "hostname": socket.gethostname(),
            "timestamp": "t",
            "last_seen": _iso(datetime.datetime.now(datetime.timezone.utc)),
            "pid": os.getppid(),
        }
        with open(FileLockManager.get_lock_file_path(proj), "w") as f:
            json.dump(lock_data, f)
        ok, msg = FileLockManager.acquire_lock(proj)
        assert ok is False
        assert "locked by" in msg.lower()


def test_acquire_lock_reacquire_when_owned():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        assert FileLockManager.acquire_lock(proj)[0] is True
        # Already owned -> re-acquire succeeds (temp+replace path)
        ok, msg = FileLockManager.acquire_lock(proj)
        assert ok is True
        FileLockManager.release_lock(proj)


def test_release_lock_invalid_path():
    assert FileLockManager.release_lock("/no/such/project.arch") is False


def test_release_lock_no_lock_file_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        # No lock file present -> returns True (nothing to release)
        assert FileLockManager.release_lock(proj) is True


def test_release_lock_owned_by_other_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        lock_data = {
            "user": "someone",
            "hostname": socket.gethostname(),
            "timestamp": "t",
            "last_seen": _iso(datetime.datetime.now(datetime.timezone.utc)),
            "pid": os.getppid(),
        }
        with open(FileLockManager.get_lock_file_path(proj), "w") as f:
            json.dump(lock_data, f)
        assert FileLockManager.release_lock(proj) is False


# --------------------------------------------------------------------------
# write_heartbeat
# --------------------------------------------------------------------------

def test_write_heartbeat_updates_last_seen_when_owned():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        FileLockManager.acquire_lock(proj)
        lock_file = FileLockManager.get_lock_file_path(proj)
        with open(lock_file) as f:
            before = json.load(f)["last_seen"]
        # Force an older last_seen, then heartbeat should refresh it
        data = json.load(open(lock_file))
        data["last_seen"] = "2000-01-01T00:00:00+00:00"
        json.dump(data, open(lock_file, "w"))
        FileLockManager.write_heartbeat(proj)
        after = json.load(open(lock_file))["last_seen"]
        assert after != "2000-01-01T00:00:00+00:00"
        FileLockManager.release_lock(proj)


def test_write_heartbeat_no_file_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "p.arch")
        open(proj, "w").close()
        # No lock file -> should not raise
        FileLockManager.write_heartbeat(proj)


def test_write_heartbeat_empty_path_is_noop():
    FileLockManager.write_heartbeat("")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

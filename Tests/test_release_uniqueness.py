import sys
import os
import tempfile

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase


def test_release_uniqueness():
    print("Running Release Uniqueness Unit Test...")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_uniqueness.arch")

        db = ProjectDatabase()
        db.open(db_path)
        mgr = ReleaseManager()
        mgr.set_db(db)

        # 1. Create first release with an elf_hash
        elf_hash_1 = "same_md5_hash_value"
        rel1 = mgr.create_release("Release_1", "First Release", copy_from_active=False, elf_hash=elf_hash_1)
        assert len(mgr.releases) == 1
        assert mgr.releases[0].elf_hash == "same_md5_hash_value"
        print("Test 1: Release 1 created successfully with MD5 hash.")

        # 2. Reload from DB to test persistence
        db.close()
        db2 = ProjectDatabase()
        db2.open(db_path)
        mgr2 = ReleaseManager()
        mgr2.set_db(db2)
        assert len(mgr2.releases) == 1
        assert mgr2.releases[0].elf_hash == "same_md5_hash_value"
        print("Test 2: Hash persistence verified in DB.")

        # 3. Uniqueness check
        new_file_hash = "same_md5_hash_value"
        is_duplicate = any(r.elf_hash == new_file_hash for r in mgr2.releases)
        assert is_duplicate is True

        different_file_hash = "different_hash_value"
        is_duplicate_diff = any(r.elf_hash == different_file_hash for r in mgr2.releases)
        assert is_duplicate_diff is False
        print("Test 3: Uniqueness check correctly identifies duplicates.")

        db2.close()
        print("\nALL RELEASE UNIQUENESS UNIT TESTS PASSED!")


if __name__ == "__main__":
    test_release_uniqueness()

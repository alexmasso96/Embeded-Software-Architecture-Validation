import sys
import os
import shutil
import tempfile

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase


def _open_db(path: str) -> ProjectDatabase:
    db = ProjectDatabase()
    db.open(path)
    return db


def test_save_as_release_handling():
    print("Running Save As Release Handling Unit Test...")

    with tempfile.TemporaryDirectory() as tmp:
        old_path = os.path.join(tmp, "old_project.arch")
        new_path = os.path.join(tmp, "new_project.arch")

        # 1. Create project with releases using DB
        old_db = _open_db(old_path)
        mgr = ReleaseManager()
        mgr.set_db(old_db)

        # 2. Create Release_1 with data
        rel1 = mgr.create_release("Release_1", "First active release")
        rel1_data = {"rows": [{"port": "A", "val": "1"}]}
        mgr._save_data(rel1, rel1_data)

        # 3. Create Release_2 with data (simulate lazy-loaded)
        rel2 = mgr.create_release("Release_2", "Second release (lazy-loaded)")
        rel2_data = {"rows": [{"port": "B", "val": "2"}]}
        mgr._save_data(rel2, rel2_data)
        rel2.data_cache = None  # simulate lazy loading

        # 4. Create a baseline
        baseline = mgr.create_baseline(
            release_index=1,  # Release_1 is at index 1 (Release_2 inserted at 0)
            baseline_name="Baseline_1",
            active_model_data={"rows": [{"port": "A", "val": "1"}]}
        )
        baseline.data_cache = None  # simulate lazy loading

        assert len(mgr.releases) == 3
        print("✓ Setup complete: 2 releases + 1 baseline created in DB.")

        old_db.close()

        # 5. "Save As" = copy the DB file to new path and rewire
        shutil.copy2(old_path, new_path)
        new_db = _open_db(new_path)

        mgr2 = ReleaseManager()
        mgr2.set_db(new_db)

        assert len(mgr2.releases) == 3
        r_names = [r.name for r in mgr2.releases]
        assert "Release_1" in r_names
        assert "Release_2" in r_names
        assert "Baseline_1" in r_names
        print("✓ Fresh manager loaded from copied DB: 3 releases found.")

        # 6. Verify data for each release
        rel1_loaded = next(r for r in mgr2.releases if r.name == "Release_1")
        data1 = mgr2._load_data(rel1_loaded)
        assert data1["rows"][0]["port"] == "A"
        print("✓ Release_1 data intact after Save As.")

        rel2_loaded = next(r for r in mgr2.releases if r.name == "Release_2")
        data2 = mgr2._load_data(rel2_loaded)
        assert data2["rows"][0]["port"] == "B"
        print("✓ Release_2 data intact after Save As.")

        base_loaded = next(r for r in mgr2.releases if r.name == "Baseline_1")
        data_base = mgr2._load_data(base_loaded)
        assert data_base["rows"][0]["port"] == "A"
        print("✓ Baseline_1 data intact after Save As.")

        # 7. Activate a release and reload data
        idx2 = mgr2.releases.index(rel2_loaded)
        r = mgr2.set_active_release(idx2)
        assert r is not None
        assert r.data_cache["rows"][0]["port"] == "B"
        print("✓ Lazy-load via set_active_release works correctly.")

        new_db.close()
        print("\nALL SAVE AS RELEASE HANDLING UNIT TESTS PASSED!")


if __name__ == "__main__":
    test_save_as_release_handling()

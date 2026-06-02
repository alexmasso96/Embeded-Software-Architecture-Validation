import sys
import os
import json
import tempfile

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase


def _make_db(path: str) -> ProjectDatabase:
    db = ProjectDatabase()
    db.open(path)
    return db


def test_baseline_features():
    print("Starting Baseline Features Unit Test...")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_baseline.arch")
        db = _make_db(db_path)

        try:
            # 1. Initialize ReleaseManager
            mgr = ReleaseManager()
            mgr.set_db(db)

            # 2. Create a normal release
            rel = mgr.create_release("Release_1.0", "First Release", copy_from_active=False)
            assert len(mgr.releases) == 1
            assert mgr.releases[0].name == "Release_1.0"
            assert not mgr.releases[0].is_baseline
            print("Test 1: Normal release creation passed.")

            # Add some sample data to release data cache
            sample_data = {
                "rows": [
                    {"TC. ID": {"text": "TC_001"}, "Input Port": {"text": "PortA"}}
                ]
            }
            mgr._save_data(rel, sample_data)

            # 3. Create a baseline
            layout_data = {
                "version": "2.0",
                "layout": [["TC. ID", "Static Text", True]],
                "settings": {"default_cyclicity": "10"}
            }

            baseline_name = "My_Custom_Baseline"
            baseline = mgr.create_baseline(0, baseline_name, layout_data, active_model_data=sample_data)

            # Check in-memory state
            assert len(mgr.releases) == 2
            assert mgr.releases[1].name == "My_Custom_Baseline"
            assert mgr.releases[1].is_baseline
            assert mgr.releases[1].parent_release_name == "Release_1.0"
            print("Test 2: Baseline creation in registry passed.")

            # Check DB state
            db_releases = db.get_all_releases()
            baseline_rows = [r for r in db_releases if r["is_baseline"]]
            assert len(baseline_rows) == 1
            assert baseline_rows[0]["name"] == "My_Custom_Baseline"

            # Validate layout stored in meta
            import json
            layout_blob = db.get_meta(f"baseline_layout_{baseline.id}")
            assert layout_blob is not None
            layout_json = json.loads(layout_blob)
            assert layout_json["settings"]["default_cyclicity"] == "10"
            print("Test 3: Baseline data and layout stored in DB.")

            # Validate rows stored in DB
            rows_from_db = db.get_release_rows(baseline.id)
            assert rows_from_db[0]["TC. ID"]["text"] == "TC_001"
            print("Test 4: Saved contents are correct.")

            # 4. Inhibit release deletion when baseline exists
            rel_idx = mgr.releases.index(rel)
            delete_result = mgr.delete_release(rel_idx)
            assert isinstance(delete_result, tuple)
            assert delete_result[0] is False
            print("Test 5: Block release deletion with baseline passed.")

            # 5. Soft-delete the baseline
            baseline_idx = mgr.releases.index(baseline)
            delete_baseline_result = mgr.delete_release(baseline_idx)
            assert delete_baseline_result is True or (
                isinstance(delete_baseline_result, tuple) and delete_baseline_result[0] is True
            )
            assert mgr.releases[baseline_idx].is_deleted is True
            print("Test 6: Baseline soft-delete passed (no filesystem required).")

            # 6. Release deletion can now succeed (no active baseline)
            rel_idx = mgr.releases.index(rel)
            delete_rel_result = mgr.delete_release(rel_idx)
            assert delete_rel_result is True or (
                isinstance(delete_rel_result, tuple) and delete_rel_result[0] is True
            )
            # Only soft-deleted baseline remains
            assert len(mgr.releases) == 1
            assert mgr.releases[0].is_baseline and mgr.releases[0].is_deleted
            print("Test 7: Release deletion post-baseline removal passed.")

            print("\nALL BASELINE FEATURE UNIT TESTS PASSED!")

        finally:
            db.close()


if __name__ == "__main__":
    test_baseline_features()

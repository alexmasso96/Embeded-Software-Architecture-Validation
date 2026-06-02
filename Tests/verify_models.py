import sys
import os
import tempfile

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Architecture_Models import ArchitectureManager, ArchitectureModel
from Application_Logic.Logic_Database import ProjectDatabase
# Smoke test UI imports (will fail if syntax error)
from UI.Dialog_Architecture_Manager import ArchitectureManagerDialog
from UI.Dialog_Architecture_Edit import ArchitectureEditDialog


def verify_logic():
    print("Starting Logic Verification...")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_arch.arch")
        db = ProjectDatabase()
        db.open(db_path)

        # 1. Init Manager with DB
        mgr = ArchitectureManager()
        mgr.set_db(db)
        assert len(mgr.models) == 1
        assert mgr.models[0].name == "Architecture_1"
        print("Test 1: Initialization Passed")

        # 2. CRUD — Create
        m2 = mgr.create_model("Model B", "In Work")
        assert len(mgr.models) == 2
        assert m2.name == "Model B"
        print("Test 2: Creation Passed")

        # 3. Duplicate
        m2_dup = mgr.create_model("Model B Copy", "Released", copy_from_index=1)
        assert len(mgr.models) == 3
        assert m2_dup.name == "Model B Copy"
        assert m2_dup.status == "Released"
        print("Test 3: Duplication Passed")

        # 4. Soft Delete
        mgr.soft_delete_model(0)  # Delete Default
        assert mgr.models[0].is_deleted is True
        assert len([m for m in mgr.models if not m.is_deleted]) == 2
        print("Test 4: Soft Delete Passed")

        # 5. Restore
        mgr.restore_model(0)
        assert mgr.models[0].is_deleted is False
        assert len([m for m in mgr.models if not m.is_deleted]) == 3
        print("Test 5: Restore Passed")

        # 6. Move — List is [Default, Model B, Copy]; Move Copy (2) to 0
        mgr.move_model(2, 0)
        assert mgr.models[0].name == "Model B Copy"
        print("Test 6: Move Passed")

        # 7. Persistence — reload from same DB
        mgr.save_registry()
        db.close()

        db2 = ProjectDatabase()
        db2.open(db_path)
        mgr2 = ArchitectureManager()
        mgr2.set_db(db2)
        assert len(mgr2.models) == 3
        assert mgr2.models[0].name == "Model B Copy"
        db2.close()
        print("Test 7: Persistence Passed")

        print("\nALL VERIFICATION STEPS PASSED")


if __name__ == "__main__":
    verify_logic()

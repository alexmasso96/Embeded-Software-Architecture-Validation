"""
Tests for #2E Phase 1 — release-keyed source store + source providers.

Covers the DB CRUD (save/list/read/has/size/delete, gzip round-trip), the digest
exclusion (adding/removing source must not change compute_content_digest), and the
FilesystemSourceProvider / DbReleaseSourceProvider parity.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Source_Store import (
    FilesystemSourceProvider, DbReleaseSourceProvider, as_provider, SourceFile,
)
from Tests.test_helpers import make_project_db


def _db_with_release(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "Model_A", "status": "In Work", "rows": []}],
        releases=[{"name": "R1.0"}],
    )
    rid = db.get_all_releases()[0]["id"]
    return db, rid


def _sample_files():
    return [
        ("src/main.c", "int main(void){ return 0; }\n"),
        ("src/util.c", "void util(void){}\n"),
        ("inc/util.h", "void util(void);\n"),
    ]


def test_source_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db, rid = _db_with_release(tmp)
        assert db.has_release_source(rid) is False

        n = db.save_release_source_files(rid, _sample_files())
        assert n == 3
        assert db.has_release_source(rid) is True

        listed = db.list_release_source_files(rid)
        assert [f["rel_path"] for f in listed] == ["inc/util.h", "src/main.c", "src/util.c"]
        # content NOT decompressed in the listing — sizes/hashes present
        assert all(f["content_hash"] for f in listed)
        assert all(f["size"] > 0 for f in listed)

        assert db.read_release_source_file(rid, "src/main.c") == "int main(void){ return 0; }\n"
        assert db.read_release_source_file(rid, "does/not/exist.c") is None
        assert db.get_release_source_total_size(rid) > 0
        assert db.get_release_ids_with_source() == {rid}
        db.close()


def test_unload_drops_only_source():
    with tempfile.TemporaryDirectory() as tmp:
        db, rid = _db_with_release(tmp)
        db.save_release_source_files(rid, _sample_files())
        # A mind map / code map for some model should survive an unload.
        mid = db.get_all_models()[0]["id"]
        db.save_model_code_map(mid, '{"functions": {}}')

        db.delete_release_source(rid)
        assert db.has_release_source(rid) is False
        assert db.list_release_source_files(rid) == []
        # map untouched
        assert db.get_model_code_map(mid) == {"functions": {}}
        db.close()


def test_source_blobs_excluded_from_integrity_digest():
    with tempfile.TemporaryDirectory() as tmp:
        db, rid = _db_with_release(tmp)
        before = db.compute_content_digest()
        db.save_release_source_files(rid, _sample_files())
        after_add = db.compute_content_digest()
        db.delete_release_source(rid)
        after_del = db.compute_content_digest()
        # Source blobs must not shift the integrity digest (excluded table).
        assert before == after_add == after_del
        db.close()


def test_save_replaces_previous_source():
    with tempfile.TemporaryDirectory() as tmp:
        db, rid = _db_with_release(tmp)
        db.save_release_source_files(rid, _sample_files())
        db.save_release_source_files(rid, [("only.c", "int x;\n")])
        listed = db.list_release_source_files(rid)
        assert [f["rel_path"] for f in listed] == ["only.c"]
        db.close()


def test_progress_callback_invoked_per_file():
    with tempfile.TemporaryDirectory() as tmp:
        db, rid = _db_with_release(tmp)
        seen = []
        db.save_release_source_files(
            rid, _sample_files(), progress=lambda rel, i, total: seen.append(rel))
        assert len(seen) == 3
        db.close()


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

def _write_tree(root):
    os.makedirs(os.path.join(root, "src"))
    os.makedirs(os.path.join(root, "build"))  # SKIP_DIRS
    with open(os.path.join(root, "src", "a.c"), "w") as f:
        f.write("int a;\n")
    with open(os.path.join(root, "src", "b.h"), "w") as f:
        f.write("int b;\n")
    with open(os.path.join(root, "build", "ignored.c"), "w") as f:
        f.write("int ignored;\n")
    with open(os.path.join(root, "notes.txt"), "w") as f:
        f.write("not source\n")


def test_filesystem_provider_skips_dirs_and_nonsource():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proj")
        os.makedirs(root)
        _write_tree(root)
        prov = FilesystemSourceProvider(root)
        rels = sorted(sf.rel_path for sf in prov.list_files())
        assert rels == ["src/a.c", "src/b.h"]  # build/ and .txt excluded
        assert prov.read_file("src/a.c") == "int a;\n"


def test_db_provider_matches_filesystem_after_import():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proj")
        os.makedirs(root)
        _write_tree(root)
        db, rid = _db_with_release(tmp)

        fs = FilesystemSourceProvider(root)
        db.save_release_source_files(rid, fs.iter_text())

        dbp = DbReleaseSourceProvider(db, rid)
        fs_rels = sorted(sf.rel_path for sf in fs.list_files())
        db_rels = sorted(sf.rel_path for sf in dbp.list_files())
        assert fs_rels == db_rels
        for rel in fs_rels:
            assert fs.read_file(rel) == dbp.read_file(rel)
        db.close()


def test_as_provider_coerces_path_and_passthrough():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "proj")
        os.makedirs(root)
        _write_tree(root)
        assert isinstance(as_provider(root), FilesystemSourceProvider)
        prov = FilesystemSourceProvider(root)
        assert as_provider(prov) is prov

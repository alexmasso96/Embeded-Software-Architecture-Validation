"""
#2E Phase 2 — consumer refactor parity.

Proves the refactored consumers (build_index, diff_source_folders, build_source_context,
hash_source_tree) produce identical results whether the source comes from a filesystem
folder or from the DB release store — i.e. AI features work unchanged off DB source.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

import Application_Logic.Logic_AI_Context as ctx
from Application_Logic.Logic_Code_Index import build_index
from Application_Logic.Logic_Source_Store import FilesystemSourceProvider, DbReleaseSourceProvider
from Tests.test_helpers import make_project_db


def _write(root, rel, text):
    p = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def _tree(root):
    _write(root, "inc/door.h", "int Door_State;\nvoid Door_Init(void);\n")
    _write(root, "src/door.c",
           "#include \"door.h\"\n"
           "int Door_State = 0;\n"
           "void Door_Init(void){ Door_State = 1; }\n"
           "void Door_Step(void){ Door_Init(); }\n")


def _db_with_source(tmp, root):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True)],
        releases=[{"name": "R1.0"}],
    )
    rid = db.get_all_releases()[0]["id"]
    db.save_release_source_files(rid, FilesystemSourceProvider(root).iter_text())
    return db, rid


def test_build_index_parity_fs_vs_db():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "code")
        os.makedirs(root)
        _tree(root)
        db, rid = _db_with_source(tmp, root)

        idx_fs = build_index(root)
        idx_db = build_index(DbReleaseSourceProvider(db, rid))

        assert set(idx_fs.functions) == set(idx_db.functions)
        assert set(idx_fs.globals) == set(idx_db.globals)
        # Call graph identical (Door_Step → Door_Init).
        assert idx_fs.call_graph.get("Door_Step") == idx_db.call_graph.get("Door_Step")
        db.close()


def test_diff_parity_fs_vs_db():
    with tempfile.TemporaryDirectory() as tmp:
        cur = os.path.join(tmp, "cur"); prev = os.path.join(tmp, "prev")
        os.makedirs(cur); os.makedirs(prev)
        _write(prev, "src/a.c", "int a = 1;\n")
        _write(cur, "src/a.c", "int a = 2;\n")   # modified
        _write(cur, "src/b.c", "int b;\n")       # added

        db = make_project_db(os.path.join(tmp, "p.arch"),
                             layout=[("Port", "PortSearchColumn", True)],
                             releases=[{"name": "cur"}, {"name": "prev"}])
        rels = {r["name"]: r["id"] for r in db.get_all_releases()}
        db.save_release_source_files(rels["cur"], FilesystemSourceProvider(cur).iter_text())
        db.save_release_source_files(rels["prev"], FilesystemSourceProvider(prev).iter_text())

        fs = {d["file_path"]: d["status"] for d in ctx.diff_source_folders(cur, prev)}
        dbd = {d["file_path"]: d["status"] for d in ctx.diff_source_folders(
            DbReleaseSourceProvider(db, rels["cur"]),
            DbReleaseSourceProvider(db, rels["prev"]))}
        assert fs == dbd == {"src/a.c": "modified", "src/b.c": "added"}
        db.close()


def test_build_source_context_parity():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "code")
        os.makedirs(root)
        _tree(root)
        db, rid = _db_with_source(tmp, root)

        kw = ["Door", "Init"]
        fs_ctx = ctx.build_source_context(root, kw)
        db_ctx = ctx.build_source_context(DbReleaseSourceProvider(db, rid), kw)
        # Same files surfaced (both reference door.c).
        assert ("door.c" in fs_ctx) == ("door.c" in db_ctx) is True
        db.close()


def test_db_diff_skips_unchanged_via_content_hash(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "code")
        os.makedirs(root)
        _tree(root)
        db, rid = _db_with_source(tmp, root)
        # Diffing a release against itself: identical content hashes → read nothing.
        reads = []
        real = DbReleaseSourceProvider.read_file
        monkeypatch.setattr(DbReleaseSourceProvider, "read_file",
                            lambda self, rel: reads.append(rel) or real(self, rel))
        diffs = ctx.diff_source_folders(DbReleaseSourceProvider(db, rid),
                                        DbReleaseSourceProvider(db, rid))
        assert diffs == []          # identical content → no changes
        assert reads == []          # content-hash gate skipped all reads
        db.close()

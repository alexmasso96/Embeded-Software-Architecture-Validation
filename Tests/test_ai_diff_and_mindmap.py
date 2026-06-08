"""
Phase 8 — code-diff engine, mind-map builder, requirements parsing, and the
separate prompt/rules keys. Pure logic, no Qt.
"""
import os
import sys
import csv
import shutil

sys.path.append(os.path.abspath("src"))

import pytest
from Application_Logic import Logic_AI_Context as ctx

FIXTURE_SRC = os.path.join(os.path.dirname(__file__), "..", "ForTesting", "AIGenTest", "src")


class FakeDB:
    def __init__(self):
        self.is_open = True
        self._m = {}
    def get_meta(self, k, default=None):
        return self._m.get(k, default)
    def set_meta(self, k, v):
        self._m[k] = v


# ---------------------------------------------------------------------------
# Source hashing + diff
# ---------------------------------------------------------------------------

def test_hash_source_tree_stable_and_sensitive(tmp_path):
    (tmp_path / "a.c").write_text("int a;")
    h1 = ctx.hash_source_tree(str(tmp_path))
    assert h1 == ctx.hash_source_tree(str(tmp_path))   # stable
    (tmp_path / "b.c").write_text("int b;")
    assert ctx.hash_source_tree(str(tmp_path)) != h1   # adding a file changes it


def test_diff_detects_changes_and_skips_unchanged_reads(tmp_path, monkeypatch):
    prev = tmp_path / "prev"; cur = tmp_path / "cur"
    prev.mkdir(); cur.mkdir()
    (prev / "a.c").write_text("int a = 1;\n")
    (prev / "b.c").write_text("int b = 1;\n")
    (prev / "c.c").write_text("int c = 1;\n")
    # a.c identical (copy2 preserves size+mtime -> stat-gate must skip the READ)
    shutil.copy2(prev / "a.c", cur / "a.c")
    (cur / "b.c").write_text("int b = 2;\n")     # modified
    (cur / "d.c").write_text("int d = 1;\n")     # added
    # c.c absent in cur -> deleted

    reads = []
    real = ctx._read_text
    monkeypatch.setattr(ctx, "_read_text", lambda p: reads.append(os.path.basename(p)) or real(p))

    diffs = ctx.diff_source_folders(str(cur), str(prev))
    by = {d["file_path"]: d["status"] for d in diffs}
    assert by.get("b.c") == "modified"
    assert by.get("d.c") == "added"
    assert by.get("c.c") == "deleted"
    assert "a.c" not in by                       # unchanged -> not reported
    assert "a.c" not in reads                     # and crucially NOT read (stat-gate)
    # unified diff retains newlines
    bdiff = next(d["unified_diff"] for d in diffs if d["file_path"] == "b.c")
    assert "int b = 2;" in bdiff and bdiff.endswith("\n")


def test_compute_diff_hash_order_independent(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "x.c").write_text("1"); (b / "x.c").write_text("2")
    h = ctx.compute_diff_hash(str(a), str(b))
    assert h == ctx.compute_diff_hash(str(a), str(b))   # stable
    (b / "x.c").write_text("3")
    assert ctx.compute_diff_hash(str(a), str(b)) != h   # sensitive


def test_diff_skips_oversize_without_reading(tmp_path, monkeypatch):
    prev = tmp_path / "p"; cur = tmp_path / "c"
    prev.mkdir(); cur.mkdir()
    (prev / "big.c").write_text("x")       # 1 byte
    (cur / "big.c").write_text("yy")       # 2 bytes -> differing size detects change
    reads = []
    monkeypatch.setattr(ctx, "_read_text", lambda p: reads.append(p) or "")
    diffs = ctx.diff_source_folders(str(cur), str(prev), skip_file_bytes=0)
    assert diffs[0]["status"] == "modified"
    assert "too large" in diffs[0]["unified_diff"]
    assert reads == []      # oversize path never reads bytes


# ---------------------------------------------------------------------------
# Mind map builder
# ---------------------------------------------------------------------------

def test_build_mind_map_signatures_no_bodies_and_bindings():
    ports = [{"name": "DoorLock", "operation": "GetLockState",
              "requirement_traces": ["REQ-1"]}]
    reqs = [{"id": "REQ-1", "text": "the door lock state shall be reported"}]
    mm = ctx.build_mind_map(FIXTURE_SRC, "DoorControl", 1, ports, reqs)
    assert mm["builder_version"] == ctx.MINDMAP_BUILDER_VERSION
    assert mm["source_hash"]
    # functions carry signature but NO body
    f = mm["functions"]["DoorControl_Init"]
    assert "DoorControl_Init" in f["signature"]
    assert "body" not in f
    assert f["file"].endswith("door_control.c")
    # port bound to at least one DoorControl_* function
    port = next(iter(mm["ports"].values()))
    assert any(n.startswith("DoorControl_") for n in port["implementing_funcs"])
    assert port["requirement_traces"] == ["REQ-1"]
    # requirement keyword-bound
    assert mm["requirements"]["REQ-1"]["implementing_funcs"]


def test_build_mind_map_empty_source():
    mm = ctx.build_mind_map("", "M", 1, [], [])
    assert mm["functions"] == {} and mm["source_hash"] == ""


def test_mind_map_to_text_budget_and_order():
    mm = ctx.build_mind_map(
        FIXTURE_SRC, "DoorControl", 1,
        [{"name": "DoorLock", "operation": "state"}],
        [{"id": "REQ-1", "text": "lock state reported"}])
    txt = ctx.mind_map_to_text(mm, budget_chars=4000)
    assert len(txt) <= 4000
    assert txt.index("## PORTS") < txt.index("## FUNCTION INDEX")


def test_mind_map_to_text_truncates_function_index_last():
    # Synthetic map with many functions but tiny budget: ports survive, function
    # index is truncated.
    mm = {
        "builder_version": ctx.MINDMAP_BUILDER_VERSION, "model_name": "M",
        "files": {}, "ports": {"0:P": {"name": "P", "operation": "op",
                                        "implementing_funcs": ["f1"], "files": [],
                                        "requirement_traces": []}},
        "requirements": {},
        "functions": {f"f{i}": {"file": "x.c", "signature": f"void f{i}(void)",
                                "calls": [], "reads": [], "writes": []}
                      for i in range(200)},
    }
    txt = ctx.mind_map_to_text(mm, budget_chars=600)
    assert len(txt) <= 600
    assert "## PORTS" in txt and "- P" in txt          # ports preserved
    assert "more functions omitted" in txt              # function index truncated


def test_mind_map_to_text_version_fallback():
    mm = {"builder_version": "0.9", "model_name": "M", "files": {},
          "ports": {}, "requirements": {}, "functions": {}}
    txt = ctx.mind_map_to_text(mm, budget_chars=4000)   # must NOT raise
    assert "regenerate" in txt.lower()


def test_mind_map_to_text_none():
    assert "no mind map" in ctx.mind_map_to_text(None).lower()


def test_mindmap_button_label():
    assert ctx.mindmap_button_label(True) == "Regenerate Mind Map"
    assert ctx.mindmap_button_label(False) == "Generate Mind Map"


# ---------------------------------------------------------------------------
# Requirements parsing
# ---------------------------------------------------------------------------

def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM-tolerant
        w = csv.writer(f); w.writerow(header)
        for r in rows:
            w.writerow(r)


def test_parse_requirements_csv_detects_columns(tmp_path):
    p = tmp_path / "reqs.csv"
    _write_csv(p, ["Requirement ID", "Description"],
               [["REQ-1", "lock the door"], ["REQ-2", "report voltage"]])
    out = ctx.parse_requirements_file(str(p))
    assert out == [{"id": "REQ-1", "text": "lock the door"},
                   {"id": "REQ-2", "text": "report voltage"}]


def test_parse_requirements_fallback_first_two_cols(tmp_path):
    p = tmp_path / "r.csv"
    _write_csv(p, ["colA", "colB"], [["A1", "desc one"]])
    out = ctx.parse_requirements_file(str(p))
    assert out[0]["id"] == "A1" and out[0]["text"] == "desc one"


def test_parse_requirements_truncates(tmp_path):
    p = tmp_path / "r.csv"
    _write_csv(p, ["id", "text"], [[f"R{i}", f"t{i}"] for i in range(5)])
    out = ctx.parse_requirements_file(str(p), max_rows=2)
    assert len(out) == 3                       # 2 + sentinel
    assert out[-1]["id"] == "..." and "3 more" in out[-1]["text"]


def test_parse_requirements_header_only(tmp_path):
    p = tmp_path / "r.csv"
    _write_csv(p, ["id", "text"], [])
    assert ctx.parse_requirements_file(str(p)) == []


# ---------------------------------------------------------------------------
# Separate prompt/rules keys
# ---------------------------------------------------------------------------

def test_separate_prompt_rules_defaults_and_persist():
    db = FakeDB()
    assert ctx.get_mindmap_prompt(db) == ctx.DEFAULT_MINDMAP_PROMPT
    assert ctx.get_mindmap_rules(db) == ctx.DEFAULT_MINDMAP_RULES
    assert ctx.get_chat_rules(db) == ctx.DEFAULT_CHAT_RULES
    ctx.set_chat_rules(db, "custom chat")
    assert ctx.get_chat_rules(db) == "custom chat"
    # Editing chat rules must not touch the Tab-3 low-level prompt/rules.
    assert ctx.get_prompt(db) == ctx.DEFAULT_PROMPT
    assert ctx.get_rules(db) == ctx.DEFAULT_RULES
    assert ctx.get_mindmap_prompt(db) == ctx.DEFAULT_MINDMAP_PROMPT


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

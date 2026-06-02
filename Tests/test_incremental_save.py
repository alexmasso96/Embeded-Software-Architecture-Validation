"""
Incremental Save & Performance Feature Tests
=============================================
Tests for:
  - upsert_model_row / upsert_model_rows_batch (DB layer)
  - delete_model_row (DB layer)
  - Lazy model loading: inactive models keep data_cache=None until accessed
  - Unique index enforcement on architecture_rows
  - rapidfuzz SymbolMatcher: score type, LRU cache, top matches
"""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.abspath("src"))

from Tests.test_helpers import make_project_db
from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Architecture_Models import ArchitectureManager, ArchitectureModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_fresh_db(tmp_dir: str, name: str = "test.arch") -> ProjectDatabase:
    path = os.path.join(tmp_dir, name)
    db = ProjectDatabase()
    db.open(path)
    return db


# ===========================================================================
# DB incremental upsert
# ===========================================================================

class TestUpsertModelRow:
    def test_insert_new_row(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.upsert_model_row(mid, 0, {"Signal": "A", "Value": "1"})
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 1
        assert rows[0]["Signal"] == "A"

    def test_update_existing_row(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.upsert_model_row(mid, 0, {"Signal": "A", "Value": "1"})
        db.upsert_model_row(mid, 0, {"Signal": "A", "Value": "UPDATED"})
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 1, "upsert must not create a duplicate row"
        assert rows[0]["Value"] == "UPDATED"

    def test_multiple_rows(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        for i in range(5):
            db.upsert_model_row(mid, i, {"Signal": f"S{i}"})
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 5
        assert [r["Signal"] for r in rows] == [f"S{i}" for i in range(5)]

    def test_rows_ordered_by_index(self, tmp_path):
        """Rows must come back in row_index order regardless of insert order."""
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        for i in reversed(range(4)):
            db.upsert_model_row(mid, i, {"n": i})
        db.commit()

        rows = db.get_model_rows(mid)
        assert [r["n"] for r in rows] == [0, 1, 2, 3]


class TestUpsertModelRowsBatch:
    def test_batch_insert(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        batch = {i: {"Signal": f"S{i}", "Value": str(i)} for i in range(10)}
        db.upsert_model_rows_batch(mid, batch)
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 10

    def test_batch_partial_update(self, tmp_path):
        """Updating a subset of rows must leave untouched rows intact."""
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        initial = {i: {"Signal": f"S{i}", "Value": "orig"} for i in range(5)}
        db.upsert_model_rows_batch(mid, initial)
        db.commit()

        # Only update rows 1 and 3
        db.upsert_model_rows_batch(mid, {1: {"Signal": "S1", "Value": "new"}, 3: {"Signal": "S3", "Value": "new"}})
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 5
        assert rows[1]["Value"] == "new"
        assert rows[3]["Value"] == "new"
        assert rows[0]["Value"] == "orig"
        assert rows[2]["Value"] == "orig"
        assert rows[4]["Value"] == "orig"

    def test_batch_idempotent(self, tmp_path):
        """Applying the same batch twice must not duplicate rows."""
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        batch = {0: {"Signal": "X"}, 1: {"Signal": "Y"}}
        db.upsert_model_rows_batch(mid, batch)
        db.upsert_model_rows_batch(mid, batch)
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 2

    def test_empty_batch_is_noop(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.upsert_model_row(mid, 0, {"Signal": "A"})
        db.commit()

        db.upsert_model_rows_batch(mid, {})
        db.commit()

        rows = db.get_model_rows(mid)
        assert len(rows) == 1


class TestDeleteModelRow:
    def test_delete_existing(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        for i in range(3):
            db.upsert_model_row(mid, i, {"Signal": f"S{i}"})
        db.commit()

        db.delete_model_row(mid, 1)
        db.commit()

        rows = db.get_model_rows(mid)
        signals = [r["Signal"] for r in rows]
        assert "S1" not in signals
        assert len(rows) == 2

    def test_delete_nonexistent_is_noop(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.upsert_model_row(mid, 0, {"Signal": "A"})
        db.commit()

        db.delete_model_row(mid, 99)  # Row 99 doesn't exist
        db.commit()

        assert len(db.get_model_rows(mid)) == 1


class TestUniqueIndexEnforcement:
    """The UNIQUE INDEX on (model_id, row_index) must prevent raw duplicates."""

    def test_raw_insert_duplicate_raises(self, tmp_path):
        import sqlite3
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.execute(
            "INSERT INTO architecture_rows (model_id, row_index, row_data) VALUES (?,?,?)",
            (mid, 0, '{"Signal":"A"}')
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO architecture_rows (model_id, row_index, row_data) VALUES (?,?,?)",
                (mid, 0, '{"Signal":"B"}')
            )

    def test_upsert_does_not_raise_on_conflict(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M1")
        db.upsert_model_row(mid, 0, {"Signal": "A"})
        # Should not raise
        db.upsert_model_row(mid, 0, {"Signal": "B"})
        db.commit()

        rows = db.get_model_rows(mid)
        assert rows[0]["Signal"] == "B"


# ===========================================================================
# Lazy model loading
# ===========================================================================

class TestLazyModelLoading:
    def test_inactive_models_start_with_no_cache(self, tmp_path):
        """After loading a project, only the active model should have data_cache populated."""
        db_path = os.path.join(str(tmp_path), "lazy.arch")
        db = make_project_db(
            db_path,
            models=[
                {"name": "Model_A", "rows": [{"Signal": "A1"}, {"Signal": "A2"}]},
                {"name": "Model_B", "rows": [{"Signal": "B1"}]},
                {"name": "Model_C", "rows": []},
            ]
        )

        mgr = ArchitectureManager()
        mgr.set_db(db)
        mgr.preload_all_models()

        active = mgr.get_active_model()
        assert active is not None
        assert active.data_cache is not None, "Active model must have data loaded"

        inactive = [m for m in mgr.models if m is not active]
        for m in inactive:
            assert m.data_cache is None, f"Inactive model '{m.name}' should not be pre-loaded"

    def test_on_demand_load_populates_cache(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "lazy2.arch")
        db = make_project_db(
            db_path,
            models=[
                {"name": "Model_A", "rows": [{"Signal": "A1"}]},
                {"name": "Model_B", "rows": [{"Signal": "B1"}, {"Signal": "B2"}]},
            ]
        )

        mgr = ArchitectureManager()
        mgr.set_db(db)
        mgr.preload_all_models()

        inactive = next(m for m in mgr.models if m is not mgr.get_active_model())
        assert inactive.data_cache is None

        mgr._load_model_data(inactive)
        assert inactive.data_cache is not None
        assert len(inactive.data_cache["rows"]) > 0

    def test_active_model_data_correct(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "lazy3.arch")
        rows = [{"Signal": f"Port_{i}", "Value": str(i)} for i in range(5)]
        db = make_project_db(
            db_path,
            models=[{"name": "Main", "rows": rows}]
        )

        mgr = ArchitectureManager()
        mgr.set_db(db)
        mgr.preload_all_models()

        active = mgr.get_active_model()
        loaded_rows = active.data_cache["rows"]
        assert len(loaded_rows) == 5
        assert loaded_rows[0]["Signal"] == "Port_0"
        assert loaded_rows[4]["Signal"] == "Port_4"


# ===========================================================================
# rapidfuzz SymbolMatcher
# ===========================================================================

class TestSymbolMatcherRapidfuzz:
    """Validate rapidfuzz-based SymbolMatcher behaves correctly."""

    def _make_matcher(self, func_names, var_names=None):
        from unittest.mock import MagicMock
        from Application_Logic.Logic_Symbol_Matcher import SymbolMatcher
        from core.elf_parser import ELFParser, Function, Symbol

        mock_parser = MagicMock(spec=ELFParser)
        mock_parser.functions = [Function(name=n, address=i, size=0, parameters=[], return_type=None)
                                  for i, n in enumerate(func_names)]
        mock_parser.global_vars_dwarf = {v: "int" for v in (var_names or [])}
        return SymbolMatcher(mock_parser)

    def test_exact_match_returns_high_score(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init", "SystemClock_Config"])
        name, score = matcher.find_best_match("HAL_GPIO_Init", threshold=70)
        assert name == "HAL_GPIO_Init"
        assert score == 100

    def test_score_is_integer(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init"])
        name, score = matcher.find_best_match("GPIO_Init", threshold=50)
        assert isinstance(score, int), f"Score must be int, got {type(score)}"

    def test_below_threshold_returns_none(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init"])
        name, score = matcher.find_best_match("completely_unrelated_function", threshold=95)
        assert name is None
        assert score == 0

    def test_empty_target_returns_none(self):
        matcher = self._make_matcher(["HAL_GPIO_Init"])
        name, score = matcher.find_best_match("", threshold=70)
        assert name is None
        assert score == 0

    def test_lru_cache_returns_same_result(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init"])
        result1 = matcher.find_best_match("GPIO_Init", threshold=60)
        result2 = matcher.find_best_match("GPIO_Init", threshold=60)
        assert result1 == result2

    def test_lru_cache_hit_count(self):
        matcher = self._make_matcher(["func_alpha", "func_beta", "func_gamma"])
        # Prime the cache
        matcher.find_best_match("func_alpha", threshold=70)
        # Cache info should report one miss, rest hits
        cache_info = matcher._cached_best_match.cache_info()
        assert cache_info.misses >= 1
        # Call again — should be a hit
        matcher.find_best_match("func_alpha", threshold=70)
        cache_info2 = matcher._cached_best_match.cache_info()
        assert cache_info2.hits >= 1

    def test_find_top_matches_returns_list_of_tuples(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init", "HAL_SPI_Init"])
        results = matcher.find_top_matches("GPIO", limit=3)
        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2
            name, score = item
            assert isinstance(name, str)
            assert isinstance(score, int)

    def test_find_top_matches_respects_limit(self):
        matcher = self._make_matcher([f"func_{i}" for i in range(20)])
        results = matcher.find_top_matches("func", limit=5)
        assert len(results) <= 5

    def test_top_matches_sorted_descending(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init", "SystemClock_Config"])
        results = matcher.find_top_matches("HAL_GPIO", limit=3)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True), "Results must be in descending score order"

    def test_top_matches_lru_cache_consistent(self):
        matcher = self._make_matcher(["alpha", "beta", "gamma"])
        r1 = matcher.find_top_matches("alpha", limit=3)
        r2 = matcher.find_top_matches("alpha", limit=3)
        assert r1 == r2

    def test_includes_variables_in_pool(self):
        matcher = self._make_matcher(
            func_names=["some_function"],
            var_names=["g_MotorSpeed", "g_MotorDirection"]
        )
        name, score = matcher.find_best_match("MotorSpeed", threshold=50)
        # Should find g_MotorSpeed from the variable pool
        assert name is not None
        assert "Motor" in name

    def test_get_matches_for_list(self):
        matcher = self._make_matcher(["HAL_GPIO_Init", "HAL_UART_Init", "SystemClock_Config"])
        port_list = ["HAL_GPIO_Init", "SystemClock_Config"]
        results = matcher.get_matches_for_list(port_list, threshold=80)
        assert len(results) == 2
        assert "HAL_GPIO_Init" in results
        assert "SystemClock_Config" in results
        for port, (matched, score) in results.items():
            assert matched is not None


# ===========================================================================
# Incremental vs full save path: round-trip integrity
# ===========================================================================

class TestIncrementalSaveRoundTrip:
    """Verify that incremental upserts produce the same DB state as full saves."""

    def test_upsert_matches_full_save(self, tmp_path):
        db_full = _open_fresh_db(str(tmp_path), "full.arch")
        db_incr = _open_fresh_db(str(tmp_path), "incr.arch")

        rows = [{"Signal": f"S{i}", "Value": str(i)} for i in range(10)]
        mid_full = db_full.create_model("M")
        mid_incr = db_incr.create_model("M")

        # Full save
        db_full.save_model_rows(mid_full, rows)
        db_full.commit()

        # Incremental upsert
        db_incr.upsert_model_rows_batch(mid_incr, {i: r for i, r in enumerate(rows)})
        db_incr.commit()

        full_rows = db_full.get_model_rows(mid_full)
        incr_rows = db_incr.get_model_rows(mid_incr)

        assert full_rows == incr_rows

    def test_partial_update_matches_expected(self, tmp_path):
        db = _open_fresh_db(str(tmp_path))
        mid = db.create_model("M")
        original = [{"Signal": f"S{i}", "Value": "orig"} for i in range(5)]
        db.save_model_rows(mid, original)
        db.commit()

        # Simulate a single dirty row being saved
        db.upsert_model_row(mid, 2, {"Signal": "S2", "Value": "CHANGED"})
        db.commit()

        rows = db.get_model_rows(mid)
        assert rows[2]["Value"] == "CHANGED"
        assert rows[0]["Value"] == "orig"
        assert rows[4]["Value"] == "orig"

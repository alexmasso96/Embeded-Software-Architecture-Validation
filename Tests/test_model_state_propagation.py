"""
Tests for #8.1 — model-state → port-state propagation.

ArchitectureManager.propagate_status_to_ports cascades a model leaving the
'In Work' state (e.g. In Work → Released/Retired) onto its rows' Port State,
but only for ports still 'In Work'. Released/Retired/Deleted ports are untouched,
and the transition is one-directional (only out of 'In Work').
"""
import os
import sys
import tempfile

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Tests.test_helpers import make_project_db


def _make_rows():
    return [
        {"Port": {"text": "p_a"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
        {"Port": {"text": "p_b"}, "Port State": {"text": "Released", "widget_text": "Released"}},
        {"Port": {"text": "p_c"}, "Port State": {"text": "Retired", "widget_text": "Retired"}},
        {"Port": {"text": "p_d"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
    ]


def _mgr(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True), ("Port State", "PortStateColumn", True)],
        models=[{"name": "Model_A", "status": "In Work", "rows": _make_rows()}],
    )
    mgr = ArchitectureManager()
    mgr.set_db(db)
    return mgr, db


def test_in_work_to_released_bumps_only_in_work_ports():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr(tmp)
        model = mgr.models[0]
        mgr._load_model_data(model)

        changed = mgr.propagate_status_to_ports(model, "In Work", "Released")
        assert changed == 2  # only the two 'In Work' ports

        states = [r["Port State"]["text"] for r in model.data_cache["rows"]]
        assert states == ["Released", "Released", "Retired", "Released"]
        # widget_text mirrors the new value so the table shows it on reload.
        assert model.data_cache["rows"][0]["Port State"]["widget_text"] == "Released"
        db.close()


def test_no_propagation_when_model_not_leaving_in_work():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr(tmp)
        model = mgr.models[0]
        mgr._load_model_data(model)

        # Released -> Retired is not an 'In Work' exit: no port changes.
        assert mgr.propagate_status_to_ports(model, "Released", "Retired") == 0
        # Staying In Work: no change.
        assert mgr.propagate_status_to_ports(model, "In Work", "In Work") == 0
        states = [r["Port State"]["text"] for r in model.data_cache["rows"]]
        assert states == ["In Work", "Released", "Retired", "In Work"]
        db.close()


def test_propagation_persists_to_db():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr(tmp)
        model = mgr.models[0]
        mgr._load_model_data(model)
        mgr.propagate_status_to_ports(model, "In Work", "Retired")

        # Re-read straight from the DB to confirm the rows were saved + committed.
        saved = db.get_model_rows(model.id)
        states = sorted(r["Port State"]["text"] for r in saved)
        assert states == ["Released", "Retired", "Retired", "Retired"]
        db.close()


# ── #8.2 — selected-ports filtering ──────────────────────────────────────────

def test_selected_ports_only_bumps_chosen():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr(tmp)
        model = mgr.models[0]
        mgr._load_model_data(model)

        # Only p_a is selected; p_d (also In Work) must stay In Work.
        changed = mgr.propagate_status_to_ports(
            model, "In Work", "Released",
            selected_ports={"p_a"}, port_name_column="Port")
        assert changed == 1
        states = {r["Port"]["text"]: r["Port State"]["text"]
                  for r in model.data_cache["rows"]}
        assert states == {"p_a": "Released", "p_b": "Released",
                          "p_c": "Retired", "p_d": "In Work"}
        db.close()


def test_selected_ports_groups_duplicate_port_names():
    # Two rows share port name 'p_x', both In Work → selecting 'p_x' bumps both.
    with tempfile.TemporaryDirectory() as tmp:
        db = make_project_db(
            os.path.join(tmp, "p.arch"),
            layout=[("Port", "PortSearchColumn", True),
                    ("Port State", "PortStateColumn", True)],
            models=[{"name": "M", "status": "In Work", "rows": [
                {"Port": {"text": "p_x"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
                {"Port": {"text": "p_x"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
                {"Port": {"text": "p_y"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
            ]}],
        )
        mgr = ArchitectureManager()
        mgr.set_db(db)
        model = mgr.models[0]
        mgr._load_model_data(model)

        changed = mgr.propagate_status_to_ports(
            model, "In Work", "Retired",
            selected_ports={"p_x"}, port_name_column="Port")
        assert changed == 2  # both p_x rows
        states = [(r["Port"]["text"], r["Port State"]["text"])
                  for r in model.data_cache["rows"]]
        assert states == [("p_x", "Retired"), ("p_x", "Retired"), ("p_y", "In Work")]
        db.close()


def test_empty_selection_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr(tmp)
        model = mgr.models[0]
        mgr._load_model_data(model)
        changed = mgr.propagate_status_to_ports(
            model, "In Work", "Released",
            selected_ports=set(), port_name_column="Port")
        assert changed == 0
        states = [r["Port State"]["text"] for r in model.data_cache["rows"]]
        assert states == ["In Work", "Released", "Retired", "In Work"]
        db.close()

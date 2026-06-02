"""
Shared helpers for DB-backed test fixtures.
All project files are single .arch SQLite files.
"""
import sys
import os

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Database import ProjectDatabase


def make_project_db(db_path: str,
                    layout=None,
                    models=None,
                    releases=None,
                    settings=None) -> ProjectDatabase:
    """
    Create a minimal .arch project file for testing.

    layout   – list of (col_name, col_type, visible) tuples
    models   – list of dicts: {name, status, rows}
    releases – list of dicts: {name, is_baseline, elf_hash, rows}
    settings – dict of project_meta k/v pairs
    """
    if os.path.exists(db_path):
        os.remove(db_path)

    db = ProjectDatabase()
    db.open(db_path)

    # Column layout
    if layout:
        db.save_column_layout(layout)

    # Settings / meta
    if settings:
        for k, v in settings.items():
            db.set_meta(k, str(v))

    # Architecture models
    for m in (models or []):
        model_id = db.create_model(m["name"], m.get("status", "In Work"))
        rows = m.get("rows", [])
        if rows:
            db.save_model_rows(model_id, rows)

    # Releases
    first_release_id = None
    for r in (releases or []):
        rid = db.create_release(
            name=r["name"],
            is_baseline=int(r.get("is_baseline", False)),
            description=r.get("description", ""),
            elf_path=r.get("elf_path", ""),
            elf_hash=r.get("elf_hash", ""),
            parent_release_name=r.get("parent_release_name", "") or None,
        )
        if first_release_id is None:
            first_release_id = rid
        rows = r.get("rows", [])
        if rows:
            db.save_release_rows(rid, rows)

    # Set first release as active by default
    if first_release_id is not None:
        db.set_active_release(first_release_id)

    # Set first model as active by default
    all_models = db.get_all_models()
    if all_models:
        db.set_ui_state("active_model_id", str(all_models[0]["id"]))

    db.commit()
    return db

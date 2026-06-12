"""
#2E — shared release-dropdown helper for the unified source pickers.

Every former "pick a source folder" control becomes a release dropdown listing
``ReleaseManager.selectable_releases()`` (real releases, no baselines). The combo's
item data is the release id; a 📄 marker flags releases that have source imported.
"""
from typing import Optional


def populate_release_combo(combo, release_manager, *, include_none=False,
                           none_label="(none)", prefer_id=None,
                           source_ids=None) -> Optional[int]:
    """Fill ``combo`` with selectable releases (item data = release id).

    Preserves the current selection if still valid; otherwise selects ``prefer_id``
    if present, else the first (newest) release. ``source_ids`` (a set of release ids
    that have source imported) adds a 📄 marker. Returns the selected release id.
    """
    combo.blockSignals(True)
    prev = combo.currentData()
    combo.clear()
    if include_none:
        combo.addItem(none_label, None)
    rels = release_manager.selectable_releases() if release_manager else []
    source_ids = source_ids or set()
    ids = []
    for r in rels:
        mark = " 📄" if r.id in source_ids else ""
        combo.addItem(f"{r.name}{mark}", r.id)
        ids.append(r.id)

    target = None
    if prev in ids:
        target = prev
    elif prefer_id in ids:
        target = prefer_id
    elif ids:
        target = ids[0]

    if target is not None:
        i = combo.findData(target)
        if i >= 0:
            combo.setCurrentIndex(i)
    elif include_none:
        combo.setCurrentIndex(0)
    combo.blockSignals(False)
    return combo.currentData()

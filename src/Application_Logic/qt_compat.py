"""
Transitional Phase 0 helper — deleted in Phase 4 with the PyQt UI.

Logic modules must be importable without PyQt6, but until the PyQt app
retires, some code paths still behave differently when running inside the
live GUI (e.g. showing a modal progress dialog). This module answers
"is the Qt GUI up?" WITHOUT importing Qt: it only looks at modules someone
else (the PyQt entry point) already loaded.
"""

import sys


def qt_widgets():
    """The live PyQt6.QtWidgets module if the GUI stack is already loaded, else None."""
    return sys.modules.get("PyQt6.QtWidgets")


def gui_active(widget=None) -> bool:
    """
    True when a QApplication exists (and ``widget``, if given, is a real QWidget).
    Always False in tests, headless runs, and the future FastAPI worker.
    """
    qtw = qt_widgets()
    if qtw is None or qtw.QApplication.instance() is None:
        return False
    return isinstance(widget, qtw.QWidget) if widget is not None else True

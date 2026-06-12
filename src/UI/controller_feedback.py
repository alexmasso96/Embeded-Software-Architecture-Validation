"""
Qt implementations of the user-interaction callbacks used by the logic mixins
(Phase 0 of the pywebview migration). Logic code expresses *intent* —
notify / ask / busy — and this mixin renders it with Qt dialogs. After Phase 1
the FastAPI worker provides the same contract via HTTP responses and SSE, and
this file retires with the rest of the PyQt UI in Phase 4.

Mixed into ArchitectureTabController (which owns ``self.main_window`` and
``self.table``).
"""

from contextlib import contextmanager

from PyQt6 import QtWidgets


class ControllerFeedbackMixin:

    # ---- notifications ------------------------------------------------

    def notify_info(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.information(self.main_window, title, message)

    def notify_warning(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.warning(self.main_window, title, message)

    def notify_error(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.critical(self.main_window, title, message)

    # ---- questions -----------------------------------------------------

    def ask_yes_no_cancel(self, title: str, message: str) -> str:
        """Returns 'yes', 'no' or 'cancel'."""
        Btn = QtWidgets.QMessageBox.StandardButton
        reply = QtWidgets.QMessageBox.question(
            self.main_window, title, message, Btn.Yes | Btn.No | Btn.Cancel
        )
        if reply == Btn.Yes:
            return "yes"
        if reply == Btn.No:
            return "no"
        return "cancel"

    def ask_text(self, title: str, label: str):
        """Returns the entered string, or None if cancelled."""
        text, ok = QtWidgets.QInputDialog.getText(self.main_window, title, label)
        return text if ok else None

    def ask_choice(self, title: str, label: str, items):
        """Returns the chosen item, or None if cancelled."""
        name, ok = QtWidgets.QInputDialog.getItem(
            self.main_window, title, label, list(items), 0, False
        )
        return name if ok else None

    def ask_open_file(self, title: str, file_filter: str):
        """Returns the chosen path, or None if cancelled."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, title, "", file_filter,
            options=QtWidgets.QFileDialog.Option(0)
        )
        return path or None

    # ---- long-running feedback ------------------------------------------

    @contextmanager
    def busy(self, text: str):
        """
        Non-modal LoadingDialog around a synchronous UI-thread operation.
        Yields a ``log(msg)`` callable that appends to the dialog's console and
        pumps the event loop so the text actually paints.

        Deliberately NON-modal: the synchronous work already blocks interaction,
        and an app-modal dialog driven via show()/close() (not exec()) can leave
        a dangling modal session on macOS that silently kills the sidebar
        buttons until the app is restarted.
        """
        from UI.loading_window import LoadingDialog
        loader = LoadingDialog(self.main_window)
        try:
            loader.ui.lbl_loading_text.setText(text)
        except Exception:
            pass
        loader.show()
        QtWidgets.QApplication.processEvents()

        def log(msg: str) -> None:
            loader.append_log(msg)
            QtWidgets.QApplication.processEvents()

        try:
            yield log
        finally:
            loader.close()
            loader.deleteLater()
            QtWidgets.QApplication.processEvents()

    # ---- table state ----------------------------------------------------

    def set_table_no_edit(self) -> None:
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

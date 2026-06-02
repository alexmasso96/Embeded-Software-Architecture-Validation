"""
Tests for Logic_Loading_Window: the background TaskWorker and the
LoadingDialog.run_task success/error flow (also exercises Logging_Handler).
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QDialog
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_Loading_Window import LoadingDialog, TaskWorker


def test_run_task_success_returns_result():
    dlg = LoadingDialog()
    ok = dlg.run_task(lambda a, b: a + b, 2, 3)
    assert ok == QDialog.DialogCode.Accepted.value
    assert dlg.result == 5
    assert dlg.error_msg is None


def test_run_task_error_sets_error_msg():
    dlg = LoadingDialog()

    def boom():
        raise RuntimeError("kaboom")

    ok = dlg.run_task(boom)
    assert ok == QDialog.DialogCode.Rejected.value
    assert dlg.result is None
    assert "kaboom" in dlg.error_msg


def test_run_task_with_kwargs():
    dlg = LoadingDialog()
    dlg.run_task(lambda x, mult=1: x * mult, 4, mult=5)
    assert dlg.result == 20


def test_append_log_writes_to_console():
    dlg = LoadingDialog()
    dlg.append_log("hello log")
    assert "hello log" in dlg.ui.plainTextEdit.toPlainText()


def test_task_worker_emits_finished(qtbot=None):
    results = []
    worker = TaskWorker(lambda: 42)
    worker.finished.connect(results.append)
    worker.run()  # run synchronously in-thread
    assert results == [42]


def test_task_worker_emits_error():
    errors = []
    worker = TaskWorker(lambda: (_ for _ in ()).throw(ValueError("bad")))
    worker.error.connect(errors.append)
    worker.run()
    assert errors and "bad" in errors[0]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

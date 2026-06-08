"""
Provider/model/status-pill panel mixin (Phase 10.5).

Shared by both AI tabs (Tab 3 generation, Tab 4 chat) so the provider dropdown,
live model discovery, status pill, and Configure/Help buttons exist in exactly
one place. Parameterised per tab via `self._provider_meta_key` /
`self._model_meta_key` so the two tabs persist their selections independently.

A consuming controller must:
  * be a QObject (for the discovery QThread parenting),
  * set `self._provider_meta_key` and `self._model_meta_key` before building,
  * provide `self.main_window` and a `self._db()` accessor,
  * add `self._build_provider_group()` somewhere in its layout.
"""
from PyQt6 import QtCore, QtWidgets

from . import Logic_AI_Providers as providers


class _ModelDiscoverThread(QtCore.QThread):
    """Query a provider's live model list off the UI thread."""
    done = QtCore.pyqtSignal(str, list)   # provider_id, models

    def __init__(self, provider_id, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id

    def run(self):
        try:
            models = providers.get_provider(self.provider_id).discover_models()
        except Exception:  # noqa: BLE001
            models = []
        self.done.emit(self.provider_id, models)


class ProviderPanelMixin:
    # set by the consuming controller before _build_provider_group()
    _provider_meta_key = "ai_sel_provider"
    _model_meta_key = "ai_sel_model"

    def _build_provider_group(self) -> QtWidgets.QGroupBox:
        self._discover = getattr(self, "_discover", None)
        grp = QtWidgets.QGroupBox("Provider")
        lay = QtWidgets.QVBoxLayout(grp)
        form = QtWidgets.QFormLayout()
        self.cmb_provider = QtWidgets.QComboBox()
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_changed)
        self.cmb_model = QtWidgets.QComboBox()
        self.cmb_model.currentIndexChanged.connect(self._persist_provider_model)
        form.addRow("Provider:", self.cmb_provider)
        form.addRow("Model:", self.cmb_model)
        lay.addLayout(form)

        self.lbl_status_pill = QtWidgets.QLabel()
        lay.addWidget(self.lbl_status_pill)

        row = QtWidgets.QHBoxLayout()
        btn_cfg = QtWidgets.QPushButton("Configure Providers…")
        btn_cfg.clicked.connect(self._open_configure)
        btn_help = QtWidgets.QPushButton("Help")
        btn_help.clicked.connect(self._open_help)
        row.addWidget(btn_cfg)
        row.addWidget(btn_help)
        lay.addLayout(row)
        return grp

    # ------------------------------------------------------------------
    def _meta(self, key):
        db = self._db()
        if db is not None and getattr(db, "is_open", False):
            try:
                return db.get_meta(key)
            except Exception:
                return None
        return None

    def _refresh_providers(self):
        cur = self.cmb_provider.currentData() or self._meta(self._provider_meta_key)
        self.cmb_provider.blockSignals(True)
        self.cmb_provider.clear()
        for p in providers.list_providers():
            mark = "●" if p.is_configured() else "○"
            self.cmb_provider.addItem(f"{mark} {p.label}", p.id)
        if cur:
            i = self.cmb_provider.findData(cur)
            if i >= 0:
                self.cmb_provider.setCurrentIndex(i)
        self.cmb_provider.blockSignals(False)
        self._on_provider_changed()

    def _on_provider_changed(self):
        pid = self.cmb_provider.currentData()
        self._populate_models(pid, providers.get_provider(pid).list_models() if pid else [])
        self._update_status_pill()
        self._persist_provider_model()
        if pid and providers.get_provider(pid).is_configured():
            if self._discover and self._discover.isRunning():
                self._discover.wait(50)
            self._discover = _ModelDiscoverThread(pid, self)
            self._discover.done.connect(self._on_models_discovered)
            self._discover.start()

    def _populate_models(self, pid, models):
        want = self.cmb_model.currentData() or self._meta(self._model_meta_key)
        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()
        for m in models:
            self.cmb_model.addItem(m["name"], m["id"])
        if want:
            i = self.cmb_model.findData(want)
            if i >= 0:
                self.cmb_model.setCurrentIndex(i)
        self.cmb_model.blockSignals(False)

    def _on_models_discovered(self, pid, models):
        if pid != self.cmb_provider.currentData() or not models:
            return
        self._populate_models(pid, models)

    def _update_status_pill(self):
        pid = self.cmb_provider.currentData()
        if not pid:
            self.lbl_status_pill.setText("○ No provider")
            return
        p = providers.get_provider(pid)
        if p.is_configured():
            self.lbl_status_pill.setText(f"● {p.label} connected")
            self.lbl_status_pill.setStyleSheet("color:#2e8b57;")
        else:
            self.lbl_status_pill.setText(f"○ {p.label} not configured — open Configure Providers")
            self.lbl_status_pill.setStyleSheet("color:#b8860b;")

    def _persist_provider_model(self):
        db = self._db()
        if db is None or not getattr(db, "is_open", False):
            return
        try:
            if self.cmb_provider.currentData():
                db.set_meta(self._provider_meta_key, self.cmb_provider.currentData())
            if self.cmb_model.currentData():
                db.set_meta(self._model_meta_key, self.cmb_model.currentData())
        except Exception:
            pass

    def _open_configure(self):
        from UI.Dialog_AI_Configure import AIConfigureDialog
        AIConfigureDialog(self.main_window).exec()
        self._refresh_providers()

    def _open_help(self):
        from UI.Dialog_AI_Help import AIHelpDialog
        AIHelpDialog(self.main_window).exec()

    def _cleanup_provider_threads(self):
        if getattr(self, "_discover", None) and self._discover.isRunning():
            self._discover.requestInterruption()
            self._discover.wait(3000)

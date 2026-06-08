"""
Configure AI Providers dialog.

Connect/disconnect each provider:
  * Copilot  — GitHub OAuth device flow (no manual token).
  * Anthropic / OpenAI / Gemini — API key (stored encrypted, never shown back).

Secrets are written to the encrypted per-user credential store
(Logic_AI_Credentials); nothing here touches the project DB.
"""
from PyQt6 import QtWidgets, QtCore, QtGui

from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Credentials as creds


class _CopilotPollThread(QtCore.QThread):
    success = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(str)

    def __init__(self, device_code, interval, expires_in, parent=None):
        super().__init__(parent)
        self._device_code = device_code
        self._interval = interval
        self._expires_in = expires_in
        self._stop = False

    def run(self):
        try:
            providers.CopilotProvider.poll_for_token(
                self._device_code, self._interval, self._expires_in,
                stop_check=lambda: self._stop,
            )
            self.success.emit()
        except Exception as e:  # noqa: BLE001 — surface any auth error to the UI
            self.failed.emit(str(e))

    def stop(self):
        self._stop = True


class AIConfigureDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure AI Providers")
        self.resize(560, 520)
        self._poll_thread = None
        self._build_ui()
        self._refresh_all_status()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)

        intro = QtWidgets.QLabel(
            "Connect one or more AI providers. Keys are stored encrypted on this "
            "computer only (never inside the project file)."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        root.addWidget(self._build_copilot_group())
        root.addWidget(self._build_key_group("anthropic", "Anthropic (Claude)",
                                              "https://console.anthropic.com/settings/keys"))
        root.addWidget(self._build_key_group("openai", "OpenAI (ChatGPT)",
                                              "https://platform.openai.com/api-keys"))
        root.addWidget(self._build_key_group("gemini", "Google Gemini",
                                              "https://aistudio.google.com/app/apikey"))

        root.addStretch()
        path_lbl = QtWidgets.QLabel(f"Store: {creds.credentials_path()}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        path_lbl.setWordWrap(True)
        root.addWidget(path_lbl)

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        root.addLayout(row)

    def _build_copilot_group(self) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox("GitHub Copilot")
        lay = QtWidgets.QVBoxLayout(grp)

        self.lbl_copilot_status = QtWidgets.QLabel()
        lay.addWidget(self.lbl_copilot_status)

        self.lbl_copilot_code = QtWidgets.QLabel(
            "Open the page below and enter this code:")
        self.lbl_copilot_code.setVisible(False)
        lay.addWidget(self.lbl_copilot_code)

        # Large, read-only, copyable field so the device code is always visible.
        self.edit_copilot_code = QtWidgets.QLineEdit()
        self.edit_copilot_code.setReadOnly(True)
        self.edit_copilot_code.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.edit_copilot_code.setMinimumHeight(48)
        self.edit_copilot_code.setStyleSheet(
            "font-size: 26px; font-weight: bold; letter-spacing: 4px;"
            "font-family: 'Courier New', monospace;")
        self.edit_copilot_code.setVisible(False)
        lay.addWidget(self.edit_copilot_code)

        row = QtWidgets.QHBoxLayout()
        self.btn_copilot_signin = QtWidgets.QPushButton("Sign In")
        self.btn_copilot_signin.clicked.connect(self._copilot_signin)
        self.btn_copilot_copy = QtWidgets.QPushButton("Copy Code")
        self.btn_copilot_copy.clicked.connect(self._copilot_copy_code)
        self.btn_copilot_copy.setVisible(False)
        self.btn_copilot_open = QtWidgets.QPushButton("Open github.com/login/device")
        self.btn_copilot_open.clicked.connect(self._copilot_open_url)
        self.btn_copilot_open.setVisible(False)
        self.btn_copilot_signout = QtWidgets.QPushButton("Sign Out")
        self.btn_copilot_signout.clicked.connect(self._copilot_signout)
        row.addWidget(self.btn_copilot_signin)
        row.addWidget(self.btn_copilot_copy)
        row.addWidget(self.btn_copilot_open)
        row.addWidget(self.btn_copilot_signout)
        row.addStretch()
        lay.addLayout(row)
        return grp

    def _build_key_group(self, provider_id, label, console_url) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox(label)
        lay = QtWidgets.QVBoxLayout(grp)

        status = QtWidgets.QLabel()
        status.setObjectName(f"status_{provider_id}")
        lay.addWidget(status)

        row = QtWidgets.QHBoxLayout()
        edit = QtWidgets.QLineEdit()
        edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("Paste API key…")
        edit.setObjectName(f"edit_{provider_id}")
        btn_save = QtWidgets.QPushButton("Save")
        btn_save.clicked.connect(lambda: self._save_key(provider_id))
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self._clear_key(provider_id))
        row.addWidget(edit)
        row.addWidget(btn_save)
        row.addWidget(btn_clear)
        lay.addLayout(row)

        link = QtWidgets.QLabel(f'<a href="{console_url}">Get an API key</a>')
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 11px;")
        lay.addWidget(link)
        return grp

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _refresh_all_status(self):
        self._refresh_copilot_status()
        for pid in ("anthropic", "openai", "gemini"):
            self._refresh_key_status(pid)

    def _refresh_copilot_status(self):
        connected = bool(creds.get_copilot_oauth_token())
        self.lbl_copilot_status.setText(
            "● Connected (signed in)" if connected else "○ Not connected")
        self.lbl_copilot_status.setStyleSheet(
            "color: #2e8b57;" if connected else "color: #b8860b;")
        self.btn_copilot_signin.setVisible(not connected)
        self.btn_copilot_signout.setVisible(connected)

    def _refresh_key_status(self, provider_id):
        status = self.findChild(QtWidgets.QLabel, f"status_{provider_id}")
        if not status:
            return
        configured = creds.is_configured(provider_id)
        status.setText("● Configured" if configured else "○ Not configured")
        status.setStyleSheet("color: #2e8b57;" if configured else "color: #b8860b;")

    # ------------------------------------------------------------------
    # API key actions
    # ------------------------------------------------------------------
    def _save_key(self, provider_id):
        edit = self.findChild(QtWidgets.QLineEdit, f"edit_{provider_id}")
        val = edit.text().strip()
        if not val:
            return
        creds.set_key(provider_id, val)
        edit.clear()
        self._refresh_key_status(provider_id)

    def _clear_key(self, provider_id):
        creds.delete_key(provider_id)
        self._refresh_key_status(provider_id)

    # ------------------------------------------------------------------
    # Copilot device flow
    # ------------------------------------------------------------------
    def _copilot_signin(self):
        try:
            data = providers.CopilotProvider.start_device_flow()
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Copilot Sign-In", str(e))
            return
        self._verification_uri = data.get("verification_uri", "https://github.com/login/device")
        user_code = data.get("user_code", "")
        self.lbl_copilot_code.setVisible(True)
        self.edit_copilot_code.setText(user_code)
        self.edit_copilot_code.setVisible(True)
        self.btn_copilot_copy.setVisible(True)
        self.btn_copilot_open.setVisible(True)
        self.btn_copilot_signin.setEnabled(False)
        self.lbl_copilot_status.setText("○ Waiting for authorization…")

        self._poll_thread = _CopilotPollThread(
            data.get("device_code", ""), int(data.get("interval", 5)),
            int(data.get("expires_in", 900)), self)
        self._poll_thread.success.connect(self._copilot_signin_ok)
        self._poll_thread.failed.connect(self._copilot_signin_failed)
        self._poll_thread.start()

    def _copilot_open_url(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._verification_uri))

    def _copilot_copy_code(self):
        QtWidgets.QApplication.clipboard().setText(self.edit_copilot_code.text())

    def _hide_code_widgets(self):
        for w in (self.lbl_copilot_code, self.edit_copilot_code,
                  self.btn_copilot_copy, self.btn_copilot_open):
            w.setVisible(False)

    def _copilot_signin_ok(self):
        self._hide_code_widgets()
        self.btn_copilot_signin.setEnabled(True)
        self._refresh_copilot_status()

    def _copilot_signin_failed(self, msg):
        self._hide_code_widgets()
        self.btn_copilot_signin.setEnabled(True)
        self._refresh_copilot_status()
        QtWidgets.QMessageBox.warning(self, "Copilot Sign-In", msg)

    def _copilot_signout(self):
        providers.get_provider("copilot").sign_out()
        self._refresh_copilot_status()

    def closeEvent(self, event):
        if self._poll_thread and self._poll_thread.isRunning():
            self._poll_thread.stop()
            self._poll_thread.wait(2000)
        super().closeEvent(event)

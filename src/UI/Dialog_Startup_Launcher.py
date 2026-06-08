from PyQt6 import QtWidgets, QtCore, QtGui

class StartupLauncherDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Architecture Validator Pro — Startup")
        self.resize(500, 380)
        self.setModal(True)
        
        # Inherit styling, hide window context help
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        # Center in parent geometry if parent is visible
        if parent:
            self.setGeometry(
                QtWidgets.QStyle.alignedRect(
                    QtCore.Qt.LayoutDirection.LeftToRight,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    self.size(),
                    parent.geometry()
                )
            )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Logo/Title
        title_label = QtWidgets.QLabel("Architecture Validator Pro", self)
        font = QtGui.QFont()
        font.setPointSize(18)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        subtitle_label = QtWidgets.QLabel("Welcome! Select an option to begin working:", self)
        subtitle_label.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        subtitle_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)
        
        layout.addSpacing(15)
        
        # Three Large Buttons
        self.btn_new = QtWidgets.QPushButton("New Project", self)
        self.btn_view_only = QtWidgets.QPushButton("Open Project (View Only)", self)
        self.btn_edit = QtWidgets.QPushButton("Open Project (Exclusive Edit)", self)
        
        for btn in [self.btn_new, self.btn_view_only, self.btn_edit]:
            btn.setFixedHeight(55)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #353535;
                    color: white;
                    border: 1px solid #444444;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px;
                }
                QPushButton:hover {
                    background-color: #5384e4;
                    border: 1px solid #5384e4;
                }
                QPushButton:pressed {
                    background-color: #2a5a9a;
                }
            """)
            layout.addWidget(btn)
            
        self.btn_new.clicked.connect(self.handle_new_project)
        self.btn_view_only.clicked.connect(self.handle_view_only)
        self.btn_edit.clicked.connect(self.handle_exclusive_edit)
        
    def handle_new_project(self):
        self.accept()
        # Defer to the next event loop tick so the dialog is fully closed first
        QtCore.QTimer.singleShot(0, self.main_window.new_project)

    def handle_view_only(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Open Project (View Only)", "",
            "Architecture Project (*.arch)",
            options=QtWidgets.QFileDialog.Option(0)
        )
        if file_path:
            self.accept()
            QtCore.QTimer.singleShot(0, lambda: self.main_window.load_project_with_mode(file_path, edit_mode=False))

    def handle_exclusive_edit(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Open Project (Exclusive Edit)", "",
            "Architecture Project (*.arch)",
            options=QtWidgets.QFileDialog.Option(0)
        )
        if file_path:
            from Application_Logic.Logic_File_Locking import FileLockManager
            success, lock_info = FileLockManager.acquire_lock(file_path)
            if success:
                self.accept()
                QtCore.QTimer.singleShot(0, lambda: self.main_window.load_project_with_mode(file_path, edit_mode=True))
            else:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Project Locked",
                    f"Could not open project in Exclusive Edit mode.\n\n{lock_info}"
                )

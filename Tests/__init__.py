import os
import sys
from pathlib import Path

# Disable startup dialog during tests to prevent timer-based event loop crashes
os.environ["ARCH_NO_STARTUP_DIALOG"] = "1"

#add the src directory to Python Path to allow importing core and other modules
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert (0, str(src_path))

# Global patch to replace QMessageBox Cocoa native popups/sheets with our custom styled PyQt dialog
from UI.StyledMessageBox import StyledMessageBox
import PyQt6.QtWidgets
PyQt6.QtWidgets.QMessageBox = StyledMessageBox
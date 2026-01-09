import logging

from PyQt6.QtCore import QObject, pyqtSignal

class Signaller (QObject):
    """
    A helper to send strings across threads or to the UI safely
    """

    text_received = pyqtSignal(str)

    def write (self, text):
        self.text_received.emit(str(text))

    def flush (self):
        # Needed for a file-like object compatibility
        pass

class QtLoggingHandler(logging.Handler):
    """
    A custom logging handler that sends records to the signaller
    """
    def __init__(self, signaller):
        super().__init__()
        self.signaller = signaller

    def emit(self, record):
        msg = self.format(record)
        # Append a new line because logging formatters usually do not include it
        self.signaller.write(msg + "\n")
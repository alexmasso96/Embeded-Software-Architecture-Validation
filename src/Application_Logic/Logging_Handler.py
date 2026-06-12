import logging

from .events import Emitter


class Signaller:
    """
    A file-like object that publishes everything written to it as a
    ``"text"`` event. Subscribers (e.g. a log console) register with
    ``signaller.events.on("text", fn)``.

    Delivery is synchronous on the writing thread — UI subscribers must
    marshal onto their GUI thread themselves (see ``_LogRelay`` in
    ``UI/loading_window.py``).
    """

    def __init__(self):
        self.events = Emitter()

    def write(self, text):
        self.events.emit("text", str(text))

    def flush(self):
        # Needed for a file-like object compatibility
        pass


class EmitterLoggingHandler(logging.Handler):
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

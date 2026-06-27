from PyQt6.QtWidgets import QMainWindow, QLabel
from PyQt6.QtCore import Qt, QTimer

from config import DEBUG_POLL_MS, LANGUAGE
from workers import SignalWorker
from translations import get_translator

t = get_translator(LANGUAGE)


class DebugWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Debug DVB-T — Signal")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(600, 80)

        self._label = QLabel(t("Waiting..."))
        self._label.setStyleSheet(
            "font-family: monospace; font-size: 14px; padding: 12px;"
            "background-color: #1a1a1a; color: #00ff00;"
        )
        self._label.setWordWrap(True)
        self.setCentralWidget(self._label)

        self._worker: SignalWorker | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(DEBUG_POLL_MS)
        self._timer.timeout.connect(self._poll)

    def _stop_polling(self):
        self._timer.stop()

    def showEvent(self, event):
        self._poll()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._stop_polling()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._stop_polling()
        super().closeEvent(event)

    def _poll(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = SignalWorker()
        self._worker.result.connect(self._label.setText)
        self._worker.start()

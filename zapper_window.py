import contextlib
import locale
import os
import socket
import subprocess
import time

import mpv
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QScrollArea, QPushButton, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence

from config import (
    BASE_URL, SSH_TUNNEL_CMD, DEFAULT_CHANNEL,
    TIMESHIFT_STEP_SECONDS, BUTTON_SIZE, CURSOR_HIDE_DELAY_MS, LANGUAGE, VDR_LIVE_PORT,
)
from workers import ChannelWorker, EPGLoaderWorker
from epg_window import EPGMainWindow
from debug_window import DebugWindow
from translations import get_translator

t = get_translator(LANGUAGE)

BUTTON_STYLE_NORMAL = """
QPushButton {
    background-color: #303030;
    color: white;
    border: 1px solid #505050;
    padding: 4px;
    text-align: left;
}
QPushButton:hover { background-color: #404040; }
"""

BUTTON_STYLE_SELECTED = """
QPushButton {
    background-color: #606060;
    color: white;
    border: 1px solid #A0A0A0;
    padding: 4px;
    text-align: left;
}
"""

BUTTON_STYLE_PLAYING = """
QPushButton {
    background-color: #206020;
    color: white;
    border: 1px solid #40A040;
    padding: 4px;
    text-align: left;
}
"""


class ZapperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        locale.setlocale(locale.LC_NUMERIC, "C")
        os.environ.setdefault("PIPEWIRE_REMOTE", "/run/user/1000/pipewire-0")
        self.setWindowTitle("Gargantua")

        self._init_state()
        self._setup_layout()
        self._setup_mpv()
        self._setup_shortcuts()
        self._start_tunnel()

        QTimer.singleShot(1500, self.load_channels)
        self.resize(1920, 1080)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.showFullScreen()
        self._hide_cursor()

    # --- Initialisation ---

    def _init_state(self):
        self.channels: list[tuple[int, str]] = []
        self.channel_buttons: list[QPushButton] = []
        self.playing_index: int | None = None
        self.selected_index: int | None = None

        self._debug_window: DebugWindow | None = None
        self._epg_window: EPGMainWindow | None = None
        self._window_stack: list = []
        self._epg_loader: EPGLoaderWorker | None = None

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(CURSOR_HIDE_DELAY_MS)
        self._cursor_timer.timeout.connect(self._hide_cursor)
        QApplication.instance().installEventFilter(self)

    def _setup_layout(self):
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(300)
        self.left_panel.setMaximumWidth(400)
        self.left_panel.setStyleSheet("background-color: #202020; color: white;")

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        left_layout.addWidget(self.scroll_area)

        self.buttons_widget = QWidget()
        self.buttons_layout = QVBoxLayout(self.buttons_widget)
        self.buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.buttons_widget)

        self.video_widget = QWidget(self)
        self.video_widget.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.video_widget, stretch=1)
        self.setCentralWidget(central)

    def _setup_mpv(self):
        one_gb = 1024 * 1024 * 1024
        self.mpv = mpv.MPV(
            wid=str(int(self.video_widget.winId())),
            vo="gpu", ao="pipewire", osc=False,
            input_default_bindings=False, input_vo_keyboard=False,
            loglevel="info", hwdec="no", vf="bwdif", 
            cache="yes", cache_pause="no",
            demuxer_max_bytes=str(one_gb),
            demuxer_max_back_bytes=str(one_gb),
           

        )

    def _setup_shortcuts(self):
        def sc(key, slot):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)
            s.activated.connect(slot)

        for key, slot in [
            ("f",                   self.toggle_fullscreen),
            ("m",                   self.toggle_mute),
            ("q",                   self.close_or_quit),
            ("d",                   self.toggle_debug),
            ("e",                   self.toggle_epg),
            ("p",                   self.zap_prev),
            ("n",                   self.zap_next),
            (Qt.Key.Key_Up,         self.move_selection_up),
            (Qt.Key.Key_Down,       self.move_selection_down),
            (Qt.Key.Key_Left,       self.seek_backward),
            (Qt.Key.Key_Right,      self.seek_forward),
            (Qt.Key.Key_Return,     self.play_selected),
            (Qt.Key.Key_Enter,      self.play_selected),
        ]:
            sc(key, slot)

    def _port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a port is open locally"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _start_tunnel(self):
        self._tunnel = None
        try:
            # Launch SSH tunnel with robust options
            cmd = SSH_TUNNEL_CMD.copy() if isinstance(SSH_TUNNEL_CMD, list) else SSH_TUNNEL_CMD
            self._tunnel = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait for tunnel to be ready (max 15 seconds)
            for _ in range(1, 16):
                if self._port_open("127.0.0.1", VDR_LIVE_PORT):
                    return  # Tunnel is ready!
                if self._tunnel.poll() is not None:
                    # Process died
                    QMessageBox.critical(self, t("VDR Error"), "Tunnel SSH s'est fermé prématurément")
                    return
                time.sleep(1)

            # Timeout
            QMessageBox.critical(self, t("VDR Error"), "Tunnel SSH non disponible après 15 secondes")
        except Exception as e:
            QMessageBox.critical(self, t("VDR Error"), f"Impossible d'ouvrir le tunnel SSH : {e}")

    # --- Channels ---

    def clear_buttons(self):
        self.channel_buttons = []
        while self.buttons_layout.count():
            item = self.buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_channels(self):
        self._worker = ChannelWorker()
        self._worker.finished.connect(self._on_channels_loaded)
        self._worker.error.connect(lambda msg: QMessageBox.critical(self, t("VDR Error"), msg))
        self._worker.start()

    def _on_channels_loaded(self, channels):
        self.channels = channels
        self.clear_buttons()
        for idx, (num, name) in enumerate(self.channels):
            btn = QPushButton(f"{num:2d}   {name}")
            btn.setFixedHeight(BUTTON_SIZE)
            btn.setStyleSheet(BUTTON_STYLE_NORMAL)
            btn.clicked.connect(self._make_zap_handler(idx))
            self.buttons_layout.addWidget(btn)
            self.channel_buttons.append(btn)
        if self.channels:
            self._select_initial_channel()

    def _select_initial_channel(self):
        idx = next((i for i, (n, _) in enumerate(self.channels) if n == DEFAULT_CHANNEL), 0)
        self.play_and_select(idx)

    def update_button_styles(self):
        for i, btn in enumerate(self.channel_buttons):
            if i == self.playing_index:
                btn.setStyleSheet(BUTTON_STYLE_PLAYING)
            elif i == self.selected_index:
                btn.setStyleSheet(BUTTON_STYLE_SELECTED)
            else:
                btn.setStyleSheet(BUTTON_STYLE_NORMAL)

    def _ensure_button_visible(self, idx: int | None):
        if idx is not None and 0 <= idx < len(self.channel_buttons):
            self.scroll_area.ensureWidgetVisible(self.channel_buttons[idx])

    def play_and_select(self, idx: int, show_osd: bool = True):
        if not (0 <= idx < len(self.channels)):
            return
        self.playing_index = idx
        self.selected_index = idx
        num, _ = self.channels[idx]
        self.play_channel(num, show_osd=show_osd)
        self.update_button_styles()
        self._ensure_button_visible(idx)

    def select_only(self, idx: int):
        if not (0 <= idx < len(self.channels)):
            return
        self.selected_index = idx
        self.update_button_styles()
        self._ensure_button_visible(idx)

    def _make_zap_handler(self, idx: int):
        def handler():
            self.play_and_select(idx)
        return handler

    # --- Playback ---

    def play_channel(self, num: int, show_osd: bool = False):
        self.mpv.loadfile(f"{BASE_URL}/{num}", "replace")
        if show_osd:
            self.mpv.command("show-text", f"Chaîne {num}", "2000", "1")

    def goto_live(self):
        if self.playing_index is None:
            return
        self.play_and_select(self.playing_index)
        with contextlib.suppress(Exception):
            self.mpv.command("show-text", "LIVE", "1000", "1")

    # --- Timeshift ---

    def seek_backward(self):
        try:
            pos = self.mpv.time_pos
        except Exception:
            pos = None

        try:
            if pos is not None and pos <= TIMESHIFT_STEP_SECONDS:
                self.mpv.command("seek", "0", "absolute+exact")
                self.mpv.command("show-text", "<< Début buffer", "800", "1")
            else:
                self.mpv.command("seek", f"-{TIMESHIFT_STEP_SECONDS}", "relative+exact")
                self.mpv.command("show-text", f"<< -{TIMESHIFT_STEP_SECONDS}s", "800", "1")
        except Exception:
            with contextlib.suppress(Exception):
                self.mpv.command("seek", "0", "absolute+exact")

    def seek_forward(self):
        try:
            pos = self.mpv.time_pos
        except Exception:
            pos = None
        try:
            dur = self.mpv.duration
        except Exception:
            dur = None

        if pos is not None and dur is not None and pos + TIMESHIFT_STEP_SECONDS >= dur:
            with contextlib.suppress(Exception):
                self.mpv.command("seek", str(dur), "absolute+exact")
                self.mpv.command("show-text", ">> Fin", "800", "1")
            return

        try:
            self.mpv.command("seek", f"{TIMESHIFT_STEP_SECONDS}", "relative+exact")
            self.mpv.command("show-text", f">> +{TIMESHIFT_STEP_SECONDS}s", "800", "1")
        except Exception:
            self.goto_live()

    # --- Channel zapping (p/n) ---

    def _zap(self, step: int):
        if self.channels:
            self.play_and_select(((self.playing_index or 0) + step) % len(self.channels))

    def zap_prev(self): self._zap(-1)
    def zap_next(self): self._zap(+1)

    # --- Keyboard navigation ---

    def _move_selection(self, step: int):
        if self.channels:
            self.select_only(((self.selected_index or 0) + step) % len(self.channels))

    def move_selection_up(self):   self._move_selection(-1)
    def move_selection_down(self): self._move_selection(+1)

    def play_selected(self):
        if not self.left_panel.isVisible():
            self.left_panel.show()
            return
        if not self.channels:
            return
        idx = self.selected_index or 0
        if idx == self.playing_index:
            self.left_panel.hide()
        else:
            self.play_and_select(idx)

    # --- Mouse cursor ---

    def _hide_cursor(self):
        QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)

    def _show_cursor(self):
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()
        self._cursor_timer.start()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            self._show_cursor()
        return super().eventFilter(obj, event)

    # --- Panel / fullscreen ---

    def toggle_fullscreen(self):
        if self.left_panel.isVisible():
            self.left_panel.hide()
        else:
            self.left_panel.show()

    # --- Mute ---

    def toggle_mute(self):
        try:
            muted = bool(self.mpv.mute)
            self.mpv.mute = not muted
            self.mpv.command("show-text", f"MUTE {'ON' if not muted else 'OFF'}", "1000", "1")
        except Exception as e:
            QMessageBox.critical(self, t("mpv Error"), str(e))

    # --- Window stack ---

    def close_or_quit(self):
        if self._window_stack:
            win = self._window_stack.pop()
            win.hide()
        else:
            self.close()

    def _push_window(self, win):
        if win in self._window_stack:
            self._window_stack.remove(win)
        self._window_stack.append(win)

    def _pop_window(self, win):
        if win in self._window_stack:
            self._window_stack.remove(win)

    # --- Secondary windows ---

    def _show_secondary_window(self, win):
        self._push_window(win)
        win.show()
        self.showFullScreen()
        QTimer.singleShot(50, win.raise_)
        QTimer.singleShot(50, win.activateWindow)

    def _hide_secondary_window(self, win):
        win.hide()
        self._pop_window(win)

    # --- Debug SNR ---

    def toggle_debug(self):
        if self._debug_window and self._debug_window.isVisible():
            self._hide_secondary_window(self._debug_window)
        else:
            if not self._debug_window:
                self._debug_window = DebugWindow()
            self._show_secondary_window(self._debug_window)

    # --- EPG ---

    def toggle_epg(self):
        if self._epg_window and self._epg_window.isVisible():
            self._hide_secondary_window(self._epg_window)
            return

        if self._epg_window:
            self._show_secondary_window(self._epg_window)
            return

        self._epg_loader = EPGLoaderWorker()
        self._epg_loader.finished.connect(self._on_epg_loaded)
        self._epg_loader.error.connect(
            lambda msg: QMessageBox.critical(self, t("EPG Error"), msg)
        )
        self._epg_loader.start()
        with contextlib.suppress(Exception):
            self.mpv.command("show-text", t("Loading EPG..."), "5000", "1")

    def _on_epg_loaded(self, epg_data: dict):
        with contextlib.suppress(Exception):
            self.mpv.command("show-text", "", "1")
        self._epg_window = EPGMainWindow(epg_data, parent=None)
        self._epg_window.channel_selected.connect(self._zap_from_epg)
        self._show_secondary_window(self._epg_window)

    def _zap_from_epg(self, ch_num: int):
        idx = next((i for i, (n, _) in enumerate(self.channels) if n == ch_num), None)
        if idx is not None:
            self.play_and_select(idx)
            self.activateWindow()

    # --- Cleanup ---

    def closeEvent(self, event):
        for win in [self._debug_window, self._epg_window]:
            if win:
                win.close()
        if self._tunnel:
            with contextlib.suppress(Exception):
                self._tunnel.terminate()
                self._tunnel.wait(timeout=3)
        with contextlib.suppress(Exception):
            self.mpv.terminate()
        super().closeEvent(event)
